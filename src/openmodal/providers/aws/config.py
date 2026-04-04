"""AWS configuration, account helpers, and GPU instance type mappings."""

from __future__ import annotations

DEFAULT_REGION = "us-east-1"
CLUSTER_NAME = "openmodal"
ECR_REPO_PREFIX = "openmodal"
S3_BUCKET_PREFIX = "openmodal"

# GPU string -> (instance_family, instance_type for 1 GPU, GPUs per instance)
GPU_MAP: dict[str, tuple[str, str, int]] = {
    "H100":      ("p5", "p5.48xlarge", 8),
    "A100-80GB": ("p4de", "p4de.24xlarge", 8),
    "A100-40GB": ("p4d", "p4d.24xlarge", 8),
    "A10G":      ("g5", "g5.xlarge", 1),
    "L4":        ("g6", "g6.xlarge", 1),
    "T4":        ("g4dn", "g4dn.xlarge", 1),
}

# instance_type -> (vCPU, RAM GB)
MACHINE_SPECS: dict[str, tuple[int, int]] = {
    "t3.small":       (2, 2),
    "t3.medium":      (2, 4),
    "t3.large":       (2, 8),
    "g4dn.xlarge":    (4, 16),
    "g5.xlarge":      (4, 16),
    "g5.2xlarge":     (8, 32),
    "g6.xlarge":      (4, 16),
    "g6.2xlarge":     (8, 32),
    "p4d.24xlarge":   (96, 1152),
    "p4de.24xlarge":  (96, 1152),
    "p5.48xlarge":    (192, 2048),
}


def get_account_id() -> str:
    import boto3
    return boto3.client("sts").get_caller_identity()["Account"]


def get_region() -> str:
    import boto3
    session = boto3.session.Session()
    return session.region_name or DEFAULT_REGION


def machine_spec_str(instance_type: str, gpu_name: str = "", gpu_count: int = 0) -> str:
    vcpu, ram_gb = MACHINE_SPECS.get(instance_type, (0, 0))
    parts = []
    if gpu_count and gpu_name:
        parts.append(f"{gpu_count}x {gpu_name}")
    if vcpu:
        parts.append(f"{vcpu} vCPU")
    if ram_gb:
        parts.append(f"{ram_gb} GB RAM")
    return ", ".join(parts) if parts else instance_type


def parse_gpu_config(gpu_str: str) -> tuple[str, str, int]:
    """Parse a GPU string like 'H100', 'A10G:2'. Returns (instance_type, gpu_name, count)."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].upper()
    count = int(parts[1]) if len(parts) > 1 else 1

    if gpu_name not in GPU_MAP:
        raise ValueError(f"Unknown GPU: {gpu_name}. Available: {list(GPU_MAP.keys())}")

    _, instance_type, _ = GPU_MAP[gpu_name]
    return instance_type, gpu_name, count
