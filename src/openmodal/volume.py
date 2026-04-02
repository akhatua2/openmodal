"""Persistent storage backed by GCS."""

from __future__ import annotations

import logging

from openmodal.providers.gcp.config import get_project, get_bucket_name
from openmodal.providers.gcp.storage import ensure_bucket

logger = logging.getLogger("openmodal.volume")


class Volume:
    def __init__(self, name: str, *, bucket: str | None = None):
        self.name = name
        self._bucket = bucket

    @classmethod
    def from_name(cls, name: str, *, create_if_missing: bool = False) -> Volume:
        vol = cls(name)
        if create_if_missing:
            vol._ensure_bucket()
        return vol

    @property
    def bucket(self) -> str:
        if self._bucket is None:
            self._bucket = f"{get_bucket_name(get_project())}-{self.name}"
        return self._bucket

    @property
    def gs_uri(self) -> str:
        return f"gs://{self.bucket}"

    def _ensure_bucket(self):
        ensure_bucket(self.gs_uri)

    def mount_command(self, mount_path: str) -> str:
        return f"mkdir -p {mount_path} && gcsfuse --implicit-dirs {self.bucket} {mount_path}"
