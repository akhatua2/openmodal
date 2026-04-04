"""One-time AKS cluster setup — creates cluster, installs NVIDIA plugin, KEDA."""

from __future__ import annotations

import logging
import subprocess

from openmodal.providers.azure.config import (
    CLUSTER_NAME,
    DEFAULT_LOCATION,
    RESOURCE_GROUP,
    get_acr_name,
    get_subscription_id,
)

logger = logging.getLogger("openmodal.azure.aks_setup")


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def cluster_exists() -> bool:
    """Check if the AKS cluster already exists."""
    result = _run(
        ["az", "aks", "show", "--name", CLUSTER_NAME, "--resource-group", RESOURCE_GROUP],
        check=False,
    )
    return result.returncode == 0


def update_kubeconfig():
    """Update local kubeconfig to point to our AKS cluster."""
    _run([
        "az", "aks", "get-credentials",
        "--name", CLUSTER_NAME,
        "--resource-group", RESOURCE_GROUP,
        "--overwrite-existing",
    ])


def setup_cluster(location: str = DEFAULT_LOCATION):
    """Create AKS cluster with KEDA addon and NVIDIA plugin."""
    subscription_id = get_subscription_id()
    acr_name = get_acr_name(subscription_id)

    # 1. Register required providers
    logger.info("Registering Azure providers...")
    for ns in ["Microsoft.ContainerService", "Microsoft.ContainerRegistry", "Microsoft.Storage"]:
        _run(["az", "provider", "register", "--namespace", ns], check=False)
    # Wait for ContainerService registration (required for AKS)
    for _ in range(60):
        result = _run(["az", "provider", "show", "--namespace", "Microsoft.ContainerService",
                        "--query", "registrationState", "-o", "tsv"], check=False)
        if "Registered" in result.stdout:
            break
        import time
        time.sleep(10)

    # 2. Create resource group
    logger.info("Creating resource group...")
    _run([
        "az", "group", "create",
        "--name", RESOURCE_GROUP,
        "--location", location,
    ], check=False)

    # 3. Create ACR
    logger.info("Creating ACR...")
    _run([
        "az", "acr", "create",
        "--name", acr_name,
        "--resource-group", RESOURCE_GROUP,
        "--location", location,
        "--sku", "Basic",
    ], check=False)

    # 4. Create AKS cluster with KEDA addon
    logger.info("Creating AKS cluster...")
    _run([
        "az", "aks", "create",
        "--name", CLUSTER_NAME,
        "--resource-group", RESOURCE_GROUP,
        "--location", location,
        "--node-count", "1",
        "--node-vm-size", "Standard_D8s_v5",
        "--enable-cluster-autoscaler",
        "--min-count", "0",
        "--max-count", "100",
        "--enable-keda",
        "--attach-acr", acr_name,
        "--generate-ssh-keys",
    ])

    # 4. Enable Node Auto-Provisioning
    _run([
        "az", "aks", "update",
        "--name", CLUSTER_NAME,
        "--resource-group", RESOURCE_GROUP,
        "--enable-node-autoprovisioning",
    ], check=False)

    # 5. Get credentials
    update_kubeconfig()

    # 5. Install NVIDIA device plugin
    logger.info("Installing NVIDIA device plugin...")
    _run([
        "kubectl", "apply", "-f",
        "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.0/deployments/static/nvidia-device-plugin.yml",
    ])

    logger.info("AKS cluster setup complete.")


def teardown_cluster():
    """Delete the AKS cluster and resource group."""
    _run([
        "az", "group", "delete",
        "--name", RESOURCE_GROUP, "--yes", "--no-wait",
    ])
