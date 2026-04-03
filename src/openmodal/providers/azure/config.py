"""Azure configuration, account helpers, and GPU VM size mappings."""

from __future__ import annotations

import subprocess

DEFAULT_LOCATION = "eastus"
RESOURCE_GROUP = "openmodal"
CLUSTER_NAME = "openmodal"
ACR_NAME = "openmodal"  # must be globally unique, will append subscription hash
STORAGE_ACCOUNT_PREFIX = "openmodal"

# GPU string -> (VM size, GPU count)
GPU_MAP: dict[str, tuple[str, int]] = {
    "H100":      ("Standard_ND96isr_H100_v5", 8),
    "A100-80GB": ("Standard_ND96amsr_A100_v4", 8),
    "A100-40GB": ("Standard_NC96ads_A100_v4", 4),
    "A10":       ("Standard_NV36ads_A10_v5", 1),
    "T4":        ("Standard_NC4as_T4_v3", 1),
    "V100":      ("Standard_NC6s_v3", 1),
}

# VM size -> (vCPU, RAM GB)
MACHINE_SPECS: dict[str, tuple[int, int]] = {
    "Standard_B2s":                (2, 4),
    "Standard_D2s_v5":             (2, 8),
    "Standard_D4s_v5":             (4, 16),
    "Standard_NC4as_T4_v3":        (4, 28),
    "Standard_NC6s_v3":            (6, 112),
    "Standard_NV36ads_A10_v5":     (36, 440),
    "Standard_NC96ads_A100_v4":    (96, 880),
    "Standard_ND96amsr_A100_v4":   (96, 1900),
    "Standard_ND96isr_H100_v5":    (96, 1900),
}


def get_subscription_id() -> str:
    result = subprocess.run(
        ["az", "account", "show", "--query", "id", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def get_acr_name(subscription_id: str) -> str:
    """Generate a globally unique ACR name from subscription ID."""
    # ACR names must be alphanumeric, 5-50 chars
    suffix = subscription_id.replace("-", "")[:8]
    return f"openmodal{suffix}"


def machine_spec_str(vm_size: str, gpu_name: str = "", gpu_count: int = 0) -> str:
    vcpu, ram_gb = MACHINE_SPECS.get(vm_size, (0, 0))
    parts = []
    if gpu_count and gpu_name:
        parts.append(f"{gpu_count}x {gpu_name}")
    if vcpu:
        parts.append(f"{vcpu} vCPU")
    if ram_gb:
        parts.append(f"{ram_gb} GB RAM")
    return ", ".join(parts) if parts else vm_size


def parse_gpu_config(gpu_str: str) -> tuple[str, str, int]:
    """Parse a GPU string like 'H100', 'T4:2'. Returns (vm_size, gpu_name, count)."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].upper()
    count = int(parts[1]) if len(parts) > 1 else 1

    if gpu_name not in GPU_MAP:
        raise ValueError(f"Unknown GPU: {gpu_name}. Available: {list(GPU_MAP.keys())}")

    vm_size, _ = GPU_MAP[gpu_name]
    return vm_size, gpu_name, count
