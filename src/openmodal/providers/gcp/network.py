"""Firewall rule management."""

from __future__ import annotations

import logging
import subprocess

from openmodal.providers.gcp.config import FIREWALL_TAG

logger = logging.getLogger("openmodal.network")


def ensure_firewall(project: str, port: int):
    rule_name = f"openmodal-allow-{port}"
    result = subprocess.run(
        ["gcloud", "compute", "firewall-rules", "describe", rule_name, "--project", project],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.debug(f"Creating firewall rule: {rule_name}")
        subprocess.run(
            ["gcloud", "compute", "firewall-rules", "create", rule_name,
             f"--allow=tcp:{port}", f"--target-tags={FIREWALL_TAG}",
             "--source-ranges=0.0.0.0/0", "--project", project],
            check=True,
        )
