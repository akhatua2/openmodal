"""Abstract base class for cloud providers."""

from __future__ import annotations

import abc

from openmodal.function import FunctionSpec


class CloudProvider(abc.ABC):
    @abc.abstractmethod
    def create_instance(self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None) -> tuple[str, str]:
        """Create an instance. Returns (instance_name, ip)."""
        ...

    @abc.abstractmethod
    def delete_instance(self, instance_name: str) -> None:
        ...

    @abc.abstractmethod
    def list_instances(self, app_name: str | None = None) -> list[dict]:
        """Returns list of dicts with keys: name, status, ip."""
        ...

    @abc.abstractmethod
    def wait_for_healthy(self, ip: str, port: int, timeout: int = 600) -> bool:
        ...

    @abc.abstractmethod
    def machine_spec_str(self, gpu_str: str) -> str:
        """Human-readable label like '1x H100, 26 vCPU, 234 GB RAM'."""
        ...

    @abc.abstractmethod
    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        ...
