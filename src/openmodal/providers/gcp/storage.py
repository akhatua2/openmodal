"""GCS bucket operations."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.storage")


def _get_compute_service_account() -> str | None:
    """Get the default compute service account for the current project."""
    result = subprocess.run(
        ["gcloud", "iam", "service-accounts", "list",
         "--filter=email~compute@developer.gserviceaccount.com",
         "--format=value(email)"],
        capture_output=True, text=True,
    )
    email = result.stdout.strip()
    return email if email else None


def _grant_bucket_access(gs_uri: str, service_account: str):
    """Grant the service account objectAdmin on the bucket so GKE nodes can mount it."""
    subprocess.run(
        ["gsutil", "iam", "ch", f"serviceAccount:{service_account}:objectAdmin", gs_uri],
        capture_output=True,
    )


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
        # Grant GKE node service account access so GCS FUSE can mount the bucket.
        # Uses bucket-level IAM (not project-level) so it works without admin permissions.
        sa = _get_compute_service_account()
        if sa:
            logger.debug(f"Granting {sa} access to {gs_uri}")
            _grant_bucket_access(gs_uri, sa)
