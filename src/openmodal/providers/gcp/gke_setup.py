"""One-time GKE cluster setup and teardown."""

from __future__ import annotations

import subprocess

from openmodal.providers.gcp.config import DEFAULT_REGION, get_project

CLUSTER_NAME = "openmodal"
GPU_NODE_POOLS = {
    "l4": {"machine_type": "g2-standard-4", "accelerator": "nvidia-l4", "count": 1},
    "a100": {"machine_type": "a2-highgpu-1g", "accelerator": "nvidia-tesla-a100", "count": 1},
    "a100-80gb": {"machine_type": "a2-ultragpu-1g", "accelerator": "nvidia-a100-80gb", "count": 1},
    "h100": {"machine_type": "a3-highgpu-1g", "accelerator": "nvidia-h100-80gb", "count": 1},
}


def _run(cmd: list[str], check: bool = True):
    subprocess.run(cmd, check=check, capture_output=True)


def _get_account() -> str:
    result = subprocess.run(
        ["gcloud", "config", "get-value", "account"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def setup_cluster(gpu_types: list[str] | None = None, region: str = DEFAULT_REGION):
    project = get_project()
    account = _get_account()
    gpu_types = gpu_types or ["h100"]

    _run([
        "gcloud", "container", "clusters", "create", CLUSTER_NAME,
        f"--region={region}",
        "--machine-type=e2-small",
        "--num-nodes=1",
        "--enable-autoscaling", "--min-nodes=0", "--max-nodes=1",
        "--addons=GcsFuseCsiDriver",
        f"--workload-pool={project}.svc.id.goog",
        "--release-channel=regular",
        f"--project={project}",
    ])

    _run([
        "gcloud", "container", "clusters", "get-credentials", CLUSTER_NAME,
        f"--region={region}", f"--project={project}",
    ])

    _run([
        "kubectl", "create", "clusterrolebinding", "openmodal-admin",
        "--clusterrole=cluster-admin",
        f"--user={account}",
    ])

    _run([
        "kubectl", "apply", "-f",
        "https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded-latest.yaml",
    ])

    _run(["helm", "repo", "add", "kedacore", "https://kedacore.github.io/charts"], check=False)
    _run(["helm", "repo", "update"])
    _run(["helm", "install", "keda", "kedacore/keda", "--namespace", "keda", "--create-namespace"])

    for gpu_type in gpu_types:
        pool = GPU_NODE_POOLS.get(gpu_type.lower())
        if not pool:
            continue
        _run([
            "gcloud", "container", "node-pools", "create", f"{gpu_type.lower()}-spot",
            f"--cluster={CLUSTER_NAME}",
            f"--region={region}",
            f"--machine-type={pool['machine_type']}",
            f"--accelerator=type={pool['accelerator']},count={pool['count']}",
            "--spot",
            "--num-nodes=0",
            "--enable-autoscaling", "--min-nodes=0", "--max-nodes=4",
            "--disk-size=200GB", "--disk-type=pd-ssd",
            f"--node-labels=gpu-type={gpu_type.lower()}",
            "--node-taints=nvidia.com/gpu=present:NoSchedule",
            f"--project={project}",
        ])


def teardown_cluster(region: str = DEFAULT_REGION):
    project = get_project()
    _run([
        "gcloud", "container", "clusters", "delete", CLUSTER_NAME,
        f"--region={region}", f"--project={project}", "--quiet",
    ])
