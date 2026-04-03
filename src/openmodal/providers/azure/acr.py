"""ACR (Azure Container Registry) operations."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.azure.acr")


def get_registry_url(acr_name: str, name: str, tag: str) -> str:
    return f"{acr_name}.azurecr.io/{name}:{tag}"


def ensure_registry(acr_name: str, resource_group: str, location: str):
    """Create ACR if it doesn't exist. Creates resource group if needed."""
    result = subprocess.run(
        ["az", "acr", "show", "--name", acr_name, "--resource-group", resource_group],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Ensure resource group exists
        subprocess.run([
            "az", "group", "create", "--name", resource_group, "--location", location,
        ], capture_output=True)
        subprocess.run([
            "az", "acr", "create",
            "--name", acr_name,
            "--resource-group", resource_group,
            "--location", location,
            "--sku", "Basic",
        ], check=True, capture_output=True)
        logger.debug(f"Created ACR: {acr_name}")


def docker_login(acr_name: str):
    """Authenticate local Docker daemon with ACR."""
    subprocess.run(
        ["az", "acr", "login", "--name", acr_name],
        check=True, capture_output=True,
    )
