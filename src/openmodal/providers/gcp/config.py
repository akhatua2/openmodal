"""GCP project configuration and GPU machine type mappings."""

from __future__ import annotations

import subprocess

GPU_MAP: dict[str, tuple[str, str, int]] = {
    "H100": ("a3-highgpu-1g", "nvidia-h100-80gb", 1),
    "H100-MEGA": ("a3-megagpu-8g", "nvidia-h100-mega-80gb", 8),
    "A100-80GB": ("a2-ultragpu-1g", "nvidia-a100-80gb", 1),
    "A100-40GB": ("a2-highgpu-1g", "nvidia-tesla-a100", 1),
    "L4": ("g2-standard-4", "nvidia-l4", 1),
}

MULTI_GPU_MACHINE_TYPES: dict[str, dict[int, str]] = {
    "H100": {1: "a3-highgpu-1g", 2: "a3-highgpu-2g", 4: "a3-highgpu-4g", 8: "a3-highgpu-8g"},
    "A100-80GB": {1: "a2-ultragpu-1g", 2: "a2-ultragpu-2g", 4: "a2-ultragpu-4g", 8: "a2-megagpu-16g"},
    "L4": {1: "g2-standard-4", 2: "g2-standard-12", 4: "g2-standard-24", 8: "g2-standard-48"},
}

MACHINE_SPECS: dict[str, tuple[int, int]] = {
    "e2-micro": (1, 1),
    "e2-small": (2, 2),
    "e2-medium": (2, 4),
    "e2-standard-4": (4, 16),
    "g2-standard-4": (4, 16),
    "g2-standard-12": (12, 48),
    "g2-standard-24": (24, 96),
    "g2-standard-48": (48, 192),
    "a2-highgpu-1g": (12, 85),
    "a2-ultragpu-1g": (12, 170),
    "a2-ultragpu-2g": (24, 340),
    "a2-ultragpu-4g": (48, 680),
    "a2-megagpu-16g": (96, 1360),
    "a3-highgpu-1g": (26, 234),
    "a3-highgpu-2g": (52, 468),
    "a3-highgpu-4g": (104, 936),
    "a3-highgpu-8g": (208, 1872),
    "a3-megagpu-8g": (208, 1872),
}


def machine_spec_str(machine_type: str, gpu_name: str = "", gpu_count: int = 0) -> str:
    vcpu, ram_gb = MACHINE_SPECS.get(machine_type, (0, 0))
    parts = []
    if gpu_count and gpu_name:
        parts.append(f"{gpu_count}x {gpu_name}")
    if vcpu:
        parts.append(f"{vcpu} vCPU")
    if ram_gb:
        parts.append(f"{ram_gb} GB RAM")
    return ", ".join(parts) if parts else machine_type


DEFAULT_ZONE = "us-central1-a"
DEFAULT_REGION = "us-central1"
ARTIFACT_REGISTRY_REPO = "openmodal"
GCS_BUCKET_PREFIX = "openmodal"


def get_project() -> str:
    result = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def get_bucket_name(project: str) -> str:
    return f"{GCS_BUCKET_PREFIX}-{project}"


def parse_gpu_config(gpu_str: str) -> tuple[str, str, int]:
    """Parse a GPU string like 'H100', 'H100:2', 'A100-80GB:1'."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].upper()
    count = int(parts[1]) if len(parts) > 1 else 1

    if gpu_name not in GPU_MAP:
        raise ValueError(f"Unknown GPU: {gpu_name}. Available: {list(GPU_MAP.keys())}")

    _, accel_type, _ = GPU_MAP[gpu_name]

    if count > 1 and gpu_name in MULTI_GPU_MACHINE_TYPES:
        machine_type = MULTI_GPU_MACHINE_TYPES[gpu_name].get(count)
        if not machine_type:
            raise ValueError(f"Unsupported count {count} for {gpu_name}")
    else:
        machine_type = GPU_MAP[gpu_name][0]

    return machine_type, accel_type, count
