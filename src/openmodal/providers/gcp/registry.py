"""Artifact Registry operations."""

from __future__ import annotations

import subprocess

from openmodal.providers.gcp.config import DEFAULT_REGION, ARTIFACT_REGISTRY_REPO


def get_registry_url(project: str, image_name: str, tag: str = "latest") -> str:
    return f"{DEFAULT_REGION}-docker.pkg.dev/{project}/{ARTIFACT_REGISTRY_REPO}/{image_name}:{tag}"


def ensure_repository(project: str):
    subprocess.run(
        ["gcloud", "artifacts", "repositories", "create", ARTIFACT_REGISTRY_REPO,
         "--repository-format=docker", f"--location={DEFAULT_REGION}", "--project", project],
        capture_output=True, text=True,
    )
