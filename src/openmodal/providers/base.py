"""Abstract base class for cloud providers."""

from __future__ import annotations

import abc
import subprocess

from openmodal.function import FunctionSpec


class CloudProvider(abc.ABC):
    @abc.abstractmethod
    def create_instance(
        self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None,
    ) -> tuple[str, str]:
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

    def preflight_check(self, spec: FunctionSpec) -> None:  # noqa: B027
        """Fast check that the provider is ready. Called before image build."""

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        """Build and push a container image. Returns the full image URI."""
        raise NotImplementedError

    def image_exists(self, image_uri: str) -> bool:
        """Check whether an image already exists in the registry."""
        raise NotImplementedError

    def create_sandbox_pod(
        self, name: str, image_uri: str | None, timeout: int = 3600,
        gpu: str | None = None, cpu: float | None = None, memory: int | None = None,
        env_vars: dict[str, str] | None = None,
    ):
        """Create an ephemeral sandbox pod/instance."""
        raise NotImplementedError

    def exec_in_pod(
        self,
        pod_name: str,
        *args: str,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        container: str = "main",
    ):
        """Execute a command in a running pod. Returns ContainerProcess."""
        raise NotImplementedError

    def copy_to_pod(self, pod_name: str, local_path: str, remote_path: str):
        """Copy a local file/directory into a running pod."""
        raise NotImplementedError

    def copy_from_pod(self, pod_name: str, remote_path: str, local_path: str):
        """Copy a file/directory from a running pod to the local filesystem."""
        raise NotImplementedError

    def stream_logs(
        self,
        instance_name: str,
        *,
        follow: bool = True,
        tail: int | None = None,
        since: str | None = None,
        include_stderr: bool = False,
    ) -> subprocess.Popen | None:
        """Stream logs from an instance. Returns a Popen object or None."""
        raise NotImplementedError

    def ensure_volume(self, name: str) -> str:
        """Create a volume if needed and return its URI/path."""
        raise NotImplementedError
