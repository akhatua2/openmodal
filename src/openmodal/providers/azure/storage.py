"""Azure Blob Storage operations for volumes."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.azure.storage")


def ensure_storage_account(account_name: str, resource_group: str, location: str):
    """Create a storage account if it doesn't exist."""
    result = subprocess.run(
        ["az", "storage", "account", "show", "--name", account_name, "--resource-group", resource_group],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run([
            "az", "storage", "account", "create",
            "--name", account_name,
            "--resource-group", resource_group,
            "--location", location,
            "--sku", "Standard_LRS",
        ], check=True, capture_output=True)
        logger.debug(f"Created storage account: {account_name}")


def ensure_container(account_name: str, container_name: str):
    """Create a blob container if it doesn't exist."""
    result = subprocess.run(
        ["az", "storage", "container", "show",
         "--name", container_name, "--account-name", account_name, "--auth-mode", "login"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run([
            "az", "storage", "container", "create",
            "--name", container_name, "--account-name", account_name, "--auth-mode", "login",
        ], check=True, capture_output=True)
        logger.debug(f"Created blob container: {container_name}")
