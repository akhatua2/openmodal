"""Sandbox — ephemeral container for interactive command execution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("openmodal.sandbox")


@dataclass
class ExecResult:
    output: str
    returncode: int


class Sandbox:
    def __init__(self, pod_name: str, provider: Any):
        self.id = pod_name
        self._provider = provider

    @classmethod
    def create(
        cls,
        *,
        image: Any = None,
        app: Any = None,
        timeout: int = 3600,
        workdir: str = "/",
    ) -> Sandbox:
        from openmodal.providers.gcp.gke import get_provider

        provider = get_provider()
        app_name = app.name if app else "sandbox"
        import uuid
        pod_name = f"{app_name}-{uuid.uuid4().hex[:8]}"

        image_uri = None
        if image is not None:
            image_uri = image.build_and_push(f"{app_name}-sandbox")

        provider.create_sandbox_pod(pod_name, image_uri, timeout)
        sandbox = cls(pod_name, provider)
        return sandbox

    def exec(self, command: str) -> ExecResult:
        return self._provider.exec_in_pod(self.id, command)

    def terminate(self):
        self._provider.delete_instance(self.id)
