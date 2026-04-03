"""Docker image building — local build + ACR push."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.azure.build")


def build_and_push(context_dir: str, image_uri: str):
    """Build a Docker image locally and push to ACR."""
    logger.debug(f"Building: {image_uri}")
    subprocess.run(
        ["docker", "build", "-t", image_uri, context_dir],
        check=True, capture_output=True,
    )
    logger.debug(f"Pushing: {image_uri}")
    subprocess.run(
        ["docker", "push", image_uri],
        check=True, capture_output=True,
    )
    logger.debug(f"Built and pushed: {image_uri}")
