"""One-time GKE cluster setup and teardown."""

from __future__ import annotations

import subprocess

from openmodal.providers.gcp.config import DEFAULT_ZONE, get_project

CLUSTER_NAME = "openmodal"
GPU_NODE_POOLS = {
    "l4": {"machine_type": "g2-standard-4", "accelerator": "nvidia-l4", "count": 1},
    "a100-80gb": {"machine_type": "a2-ultragpu-1g", "accelerator": "nvidia-a100-80gb", "count": 1},
    "h100": {"machine_type": "a3-highgpu-1g", "accelerator": "nvidia-h100-80gb", "count": 1},
}


def setup_cluster(gpu_types: list[str] | None = None, zone: str = DEFAULT_ZONE):
    project = get_project()
    gpu_types = gpu_types or ["l4"]

    subprocess.run([
        "gcloud", "container", "clusters", "create", CLUSTER_NAME,
        f"--zone={zone}",
        "--machine-type=e2-small",
        "--num-nodes=1",
        "--enable-autoscaling", "--min-nodes=0", "--max-nodes=1",
        "--addons=GcsFuseCsiDriver",
        "--release-channel=regular",
        f"--project={project}",
    ], check=True)

    subprocess.run([
        "gcloud", "container", "clusters", "get-credentials", CLUSTER_NAME,
        f"--zone={zone}", f"--project={project}",
    ], check=True)

    subprocess.run([
        "kubectl", "apply", "-f",
        "https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded-latest.yaml",
    ], check=True)

    for gpu_type in gpu_types:
        pool = GPU_NODE_POOLS.get(gpu_type.lower())
        if not pool:
            continue
        subprocess.run([
            "gcloud", "container", "node-pools", "create", f"{gpu_type.lower()}-pool",
            f"--cluster={CLUSTER_NAME}",
            f"--zone={zone}",
            f"--machine-type={pool['machine_type']}",
            f"--accelerator=type={pool['accelerator']},count={pool['count']}",
            "--num-nodes=0",
            "--enable-autoscaling", "--min-nodes=0", "--max-nodes=4",
            "--disk-size=200GB", "--disk-type=pd-ssd",
            f"--node-labels=gpu-type={gpu_type.lower()}",
            "--node-taints=nvidia.com/gpu=present:NoSchedule",
            f"--project={project}",
        ], check=True)


def teardown_cluster(zone: str = DEFAULT_ZONE):
    project = get_project()
    subprocess.run([
        "gcloud", "container", "clusters", "delete", CLUSTER_NAME,
        f"--zone={zone}", f"--project={project}", "--quiet",
    ], check=True)
