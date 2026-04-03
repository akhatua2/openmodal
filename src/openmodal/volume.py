"""Persistent storage — cloud-agnostic volume abstraction."""

from __future__ import annotations

import logging

logger = logging.getLogger("openmodal.volume")


class Volume:
    def __init__(self, name: str, *, bucket: str | None = None):
        self.name = name
        self._bucket = bucket

    @classmethod
    def from_name(cls, name: str, *, create_if_missing: bool = False) -> Volume:
        vol = cls(name)
        if create_if_missing:
            vol.ensure()
        return vol

    @property
    def bucket(self) -> str:
        if self._bucket is None:
            # Resolve bucket via provider (backward compatible)
            self.ensure()
        return self._bucket

    @property
    def gs_uri(self) -> str:
        return f"gs://{self.bucket}"

    def ensure(self, provider=None):
        """Ensure the backing storage exists. Uses provider if given, else falls back to GCP."""
        if provider is None:
            from openmodal.providers import get_provider
            provider = get_provider()
        uri = provider.ensure_volume(self.name)
        # Update cached bucket from the URI if it's a gs:// URI
        if uri.startswith("gs://"):
            self._bucket = uri.removeprefix("gs://")
        return uri

    def _ensure_bucket(self):
        """Backward-compatible alias."""
        self.ensure()

    def mount_command(self, mount_path: str) -> str:
        return f"mkdir -p {mount_path} && gcsfuse --implicit-dirs {self.bucket} {mount_path}"
