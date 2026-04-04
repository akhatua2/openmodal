"""Docker image building via ACR Tasks (remote) or local docker."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.azure.build")


def acr_build(context_dir: str, image_uri: str, acr_name: str):
    """Build a Docker image remotely using ACR Tasks. No local Docker needed."""
    # image_uri is like "myacr.azurecr.io/name:tag" — ACR Tasks wants "name:tag"
    image_tag = image_uri.split(".azurecr.io/", 1)[1]
    logger.debug(f"ACR build: {image_tag}")
    subprocess.run(
        ["az", "acr", "build", "--registry", acr_name, "--image", image_tag, context_dir],
        check=True, capture_output=True,
    )
    logger.debug(f"Built: {image_uri}")
