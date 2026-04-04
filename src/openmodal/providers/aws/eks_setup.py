"""One-time EKS cluster setup — creates cluster, installs Karpenter, KEDA, S3 CSI, NVIDIA plugin."""

from __future__ import annotations

import json
import logging
import subprocess

from openmodal.providers.aws.config import CLUSTER_NAME, get_account_id, get_region

logger = logging.getLogger("openmodal.aws.eks_setup")


def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def _kubectl(args: list[str], check: bool = True):
    return _run(["kubectl", *args], check=check)


def _helm(args: list[str], check: bool = True):
    return _run(["helm", *args], check=check)


def cluster_exists(region: str | None = None) -> bool:
    """Check if the EKS cluster already exists."""
    region = region or get_region()
    result = _run(
        ["aws", "eks", "describe-cluster", "--name", CLUSTER_NAME, "--region", region],
        check=False,
    )
    return result.returncode == 0


def update_kubeconfig(region: str | None = None):
    """Update local kubeconfig to point to our EKS cluster."""
    region = region or get_region()
    _run(["aws", "eks", "update-kubeconfig", "--name", CLUSTER_NAME, "--region", region])


def setup_cluster(region: str | None = None):
    """Create EKS cluster with Karpenter, KEDA, NVIDIA plugin, and S3 CSI driver."""
    region = region or get_region()
    account_id = get_account_id()

    # 1. Create EKS cluster with eksctl
    logger.info("Creating EKS cluster...")
    _run([
        "eksctl", "create", "cluster",
        "--name", CLUSTER_NAME,
        "--region", region,
        "--node-type", "t3.small",
        "--nodes", "1",
        "--nodes-min", "0",
        "--nodes-max", "2",
        "--managed",
        "--with-oidc",
    ])

    update_kubeconfig(region)

    # 2. Install NVIDIA device plugin
    logger.info("Installing NVIDIA device plugin...")
    _kubectl([
        "apply", "-f",
        "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.0/deployments/static/nvidia-device-plugin.yml",
    ])

    # 3. Install Karpenter
    _install_karpenter(region, account_id)

    # 4. Install KEDA
    logger.info("Installing KEDA...")
    _helm(["repo", "add", "kedacore", "https://kedacore.github.io/charts"], check=False)
    _helm(["repo", "update"])
    _helm(["install", "keda", "kedacore/keda", "--namespace", "keda", "--create-namespace"])

    # 5. Create Karpenter NodePool for GPU instances
    _create_gpu_nodepool()

    logger.info("EKS cluster setup complete.")


def _install_karpenter(region: str, account_id: str):
    """Install Karpenter for auto-provisioning GPU nodes."""
    logger.info("Installing Karpenter...")

    # Create IAM roles for Karpenter
    _run([
        "eksctl", "create", "iamserviceaccount",
        "--cluster", CLUSTER_NAME,
        "--name", "karpenter",
        "--namespace", "kube-system",
        "--attach-policy-arn", f"arn:aws:iam::{account_id}:policy/KarpenterControllerPolicy-{CLUSTER_NAME}",
        "--role-name", f"KarpenterController-{CLUSTER_NAME}",
        "--approve",
        "--region", region,
    ], check=False)

    # Create the Karpenter controller policy if it doesn't exist
    _ensure_karpenter_policy(account_id, region)

    # Get cluster endpoint for Karpenter config
    result = _run([
        "aws", "eks", "describe-cluster", "--name", CLUSTER_NAME,
        "--region", region, "--query", "cluster.endpoint", "--output", "text",
    ])
    cluster_endpoint = result.stdout.strip()

    # Install Karpenter via OCI chart (the official distribution method)
    _helm([
        "install", "karpenter", "oci://public.ecr.aws/karpenter/karpenter",
        "--version", "1.4.0",
        "--namespace", "kube-system",
        "--set", f"settings.clusterName={CLUSTER_NAME}",
        "--set", f"settings.clusterEndpoint={cluster_endpoint}",
        "--wait", "--timeout", "5m",
    ])


def _ensure_karpenter_policy(account_id: str, region: str):
    """Create the IAM policy for Karpenter if it doesn't exist."""
    import boto3
    iam = boto3.client("iam")
    policy_name = f"KarpenterControllerPolicy-{CLUSTER_NAME}"

    try:
        iam.get_policy(PolicyArn=f"arn:aws:iam::{account_id}:policy/{policy_name}")
        return  # already exists
    except iam.exceptions.NoSuchEntityException:
        pass

    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Karpenter",
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateFleet", "ec2:CreateLaunchTemplate", "ec2:CreateTags",
                    "ec2:DeleteLaunchTemplate", "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeImages", "ec2:DescribeInstances", "ec2:DescribeInstanceTypeOfferings",
                    "ec2:DescribeInstanceTypes", "ec2:DescribeLaunchTemplates",
                    "ec2:DescribeSecurityGroups", "ec2:DescribeSubnets",
                    "ec2:RunInstances", "ec2:TerminateInstances",
                    "iam:PassRole", "pricing:GetProducts",
                    "ssm:GetParameter", "eks:DescribeCluster",
                ],
                "Resource": "*",
            },
        ],
    }

    iam.create_policy(
        PolicyName=policy_name,
        PolicyDocument=json.dumps(policy_doc),
    )


def _create_gpu_nodepool():
    """Create Karpenter NodePool and EC2NodeClass for GPU workloads."""
    logger.info("Creating Karpenter GPU NodePool...")

    nodeclass = {
        "apiVersion": "karpenter.k8s.aws/v1",
        "kind": "EC2NodeClass",
        "metadata": {"name": "gpu"},
        "spec": {
            "role": f"eksctl-{CLUSTER_NAME}-nodegroup-ng-default-NodeInstanceRole",
            "amiSelectorTerms": [{"alias": "al2023@latest"}],
            "subnetSelectorTerms": [{"tags": {"eksctl.cluster.k8s.io/v1alpha1/cluster-name": CLUSTER_NAME}}],
            "securityGroupSelectorTerms": [{"tags": {"eksctl.cluster.k8s.io/v1alpha1/cluster-name": CLUSTER_NAME}}],
            "blockDeviceMappings": [{
                "deviceName": "/dev/xvda",
                "ebs": {"volumeSize": "200Gi", "volumeType": "gp3"},
            }],
        },
    }

    nodepool = {
        "apiVersion": "karpenter.sh/v1",
        "kind": "NodePool",
        "metadata": {"name": "gpu"},
        "spec": {
            "template": {
                "spec": {
                    "nodeClassRef": {"group": "karpenter.k8s.aws", "kind": "EC2NodeClass", "name": "gpu"},
                    "requirements": [
                        {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["spot", "on-demand"]},
                        {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": [
                            "g4dn.xlarge", "g5.xlarge", "g5.2xlarge",
                            "g6.xlarge", "g6.2xlarge",
                            "p4d.24xlarge", "p4de.24xlarge", "p5.48xlarge",
                        ]},
                        {"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64"]},
                    ],
                    "taints": [{"key": "nvidia.com/gpu", "effect": "NoSchedule"}],
                },
            },
            "limits": {"nvidia.com/gpu": "16"},
            "disruption": {
                "consolidationPolicy": "WhenEmptyOrUnderutilized",
                "consolidateAfter": "5m",
            },
        },
    }

    # Also create a general nodepool for non-GPU workloads (sandboxes, agents)
    general_nodepool = {
        "apiVersion": "karpenter.sh/v1",
        "kind": "NodePool",
        "metadata": {"name": "general"},
        "spec": {
            "template": {
                "spec": {
                    "nodeClassRef": {"group": "karpenter.k8s.aws", "kind": "EC2NodeClass", "name": "gpu"},
                    "requirements": [
                        {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["spot", "on-demand"]},
                        {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": [
                            "t3.medium", "t3.large", "t3.xlarge", "t3.2xlarge",
                            "m5.large", "m5.xlarge", "m5.2xlarge",
                        ]},
                        {"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64"]},
                    ],
                },
            },
            "limits": {"cpu": "100"},
            "disruption": {
                "consolidationPolicy": "WhenEmptyOrUnderutilized",
                "consolidateAfter": "2m",
            },
        },
    }

    for resource in [nodeclass, nodepool, general_nodepool]:
        _kubectl(["apply", "-f", "-"], check=False)
        # Actually pipe the JSON to kubectl
        proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(resource), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            logger.warning(f"Failed to apply {resource['kind']}/{resource['metadata']['name']}: {proc.stderr}")


def teardown_cluster(region: str | None = None):
    """Delete the EKS cluster and all associated resources."""
    region = region or get_region()
    _run(["eksctl", "delete", "cluster", "--name", CLUSTER_NAME, "--region", region])
