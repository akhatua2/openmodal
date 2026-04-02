"""Abstract base class for cloud providers."""

from __future__ import annotations

import abc

from openmodal.function import FunctionSpec


class CloudProvider(abc.ABC):
    @abc.abstractmethod
    def create_instance(self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None) -> tuple[str, str]:
        """Create a VM instance. Returns (instance_name, ip)."""
        ...

    @abc.abstractmethod
    def delete_instance(self, instance_name: str) -> None:
        """Delete a VM instance by name."""
        ...

    @abc.abstractmethod
    def list_instances(self, app_name: str | None = None) -> list[dict]:
        """List running instances, optionally filtered by app name."""
        ...

    @abc.abstractmethod
    def wait_for_healthy(self, ip: str, port: int, timeout: int = 600) -> bool:
        """Poll a health endpoint until it returns 200 or timeout."""
        ...
