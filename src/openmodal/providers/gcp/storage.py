"""GCS bucket operations."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.storage")


def ensure_bucket(gs_uri: str):
    result = subprocess.run(["gsutil", "ls", "-b", gs_uri], capture_output=True, text=True)
    if result.returncode != 0:
        logger.debug(f"Creating bucket: {gs_uri}")
        subprocess.run(["gsutil", "mb", "-l", "us-central1", gs_uri], check=True)
