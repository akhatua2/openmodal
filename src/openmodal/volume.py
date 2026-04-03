"""Persistent storage — cloud-agnostic volume abstraction."""

from __future__ import annotations

import logging

logger = logging.getLogger("openmodal.volume")


class Volume:
    def __init__(self, name: str, *, uri: str | None = None):
        self.name = name
        self._uri = uri
        self._create_if_missing = False

    @classmethod
    def from_name(cls, name: str, *, create_if_missing: bool = False) -> Volume:
        vol = cls(name)
        vol._create_if_missing = create_if_missing
        return vol

    @property
    def uri(self) -> str:
        if self._uri is None:
            self.ensure()
        assert self._uri is not None
        return self._uri

    def ensure(self, provider=None):
        """Ensure the backing storage exists. Uses provider if given, else auto-detects."""
        if provider is None:
            from openmodal.providers import get_provider
            provider = get_provider()
        self._uri = provider.ensure_volume(self.name)
        return self._uri

    def sync_down_command(self, mount_path: str) -> str:
        """CLI command to download cloud storage contents to a local path."""
        uri = self.uri
        if uri.startswith("gs://"):
            return f"mkdir -p {mount_path} && gcloud storage rsync {uri} {mount_path} --recursive"
        elif uri.startswith("s3://"):
            return f"mkdir -p {mount_path} && aws s3 sync {uri} {mount_path}"
        elif uri.startswith("azure://"):
            account, container = uri.removeprefix("azure://").split("/", 1)
            return (
                f"mkdir -p {mount_path} && "
                f"az storage blob download-batch --account-name {account} "
                f"-s {container} -d {mount_path} --auth-mode login"
            )
        return "true"

    def sync_up_command(self, mount_path: str) -> str:
        """CLI command to upload local path contents back to cloud storage."""
        uri = self.uri
        if uri.startswith("gs://"):
            return f"gcloud storage rsync {mount_path} {uri} --recursive"
        elif uri.startswith("s3://"):
            return f"aws s3 sync {mount_path} {uri}"
        elif uri.startswith("azure://"):
            account, container = uri.removeprefix("azure://").split("/", 1)
            return (
                f"az storage blob upload-batch --account-name {account} "
                f"-d {container} -s {mount_path} --auth-mode login --overwrite"
            )
        return "true"
