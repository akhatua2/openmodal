"""GCS bucket operations."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.storage")


def ensure_bucket(gs_uri: str):
    result = subprocess.run(
        ["gcloud", "storage", "buckets", "describe", gs_uri],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.debug(f"Creating bucket: {gs_uri}")
        subprocess.run(
            ["gcloud", "storage", "buckets", "create", gs_uri, "--location=us-central1"],
            capture_output=True, check=True,
        )
