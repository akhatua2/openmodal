"""Docker image building via Cloud Build or local docker."""

from __future__ import annotations

import subprocess


def cloud_build(context_dir: str, image_uri: str, project: str):
    subprocess.run(
        ["gcloud", "builds", "submit", context_dir,
         f"--tag={image_uri}", "--timeout=3600",
         "--machine-type=e2-highcpu-32", "--project", project],
        check=True,
        capture_output=True,
    )


def local_build(context_dir: str, image_uri: str):
    subprocess.run(["docker", "build", "-t", image_uri, context_dir], check=True)
    subprocess.run(["docker", "push", image_uri], check=True)
