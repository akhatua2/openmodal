"""Sandbox — Modal-compatible ephemeral container for interactive execution."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Collection

from openmodal._async_utils import _AioWrapper
from openmodal.process import ContainerProcess


@dataclass
class ExecResult:
    output: str
    returncode: int


class _MethodAio:
    """Descriptor that makes method.aio work on instances."""
    def __init__(self, method_name):
        self._method_name = method_name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        method = getattr(obj, self._method_name)

        async def aio_wrapper(*args, **kwargs):
            return await asyncio.to_thread(method, *args, **kwargs)

        method.aio = aio_wrapper
        return method


class _Filesystem:
    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    @property
    def copy_from_local(self):
        def fn(source_path, target_path):
            self._sandbox._provider.copy_to_pod(self._sandbox.object_id, str(source_path), target_path)

        async def aio(source_path, target_path):
            return await asyncio.to_thread(fn, source_path, target_path)

        fn.aio = aio
        return fn

    @property
    def copy_to_local(self):
        def fn(source_path, target_path):
            self._sandbox._provider.copy_from_pod(self._sandbox.object_id, source_path, str(target_path))

        async def aio(source_path, target_path):
            return await asyncio.to_thread(fn, source_path, target_path)

        fn.aio = aio
        return fn


class Sandbox:
    def __init__(self, pod_name: str, provider: Any):
        self._pod_name = pod_name
        self._provider = provider
        self.filesystem = _Filesystem(self)

    @property
    def object_id(self) -> str:
        return self._pod_name

    @property
    def id(self) -> str:
        return self._pod_name

    @staticmethod
    def _do_create(
        *entrypoint_args: str,
        app: Any = None,
        image: Any = None,
        name: str | None = None,
        timeout: int = 3600,
        idle_timeout: int | None = None,
        workdir: str | None = None,
        cpu: float | None = None,
        memory: int | None = None,
        gpu: str | None = None,
        block_network: bool = False,
        secrets: Collection[Any] | None = None,
        volumes: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
        **kwargs,
    ) -> Sandbox:
        from openmodal.providers.gcp.gke import get_provider

        import re
        provider = get_provider()
        app_name = app.name if app else "sandbox"
        safe_name = re.sub(r'[^a-z0-9-]', '-', app_name.lower()).strip('-')
        pod_name = name or f"{safe_name}-{uuid.uuid4().hex[:8]}"
        pod_name = re.sub(r'[^a-z0-9-]', '-', pod_name.lower()).strip('-')[:63]

        image_uri = None
        if image is not None:
            image_uri = image.build_and_push(f"{safe_name}-sandbox")

        env_vars = dict(env or {})
        for secret in (secrets or []):
            if hasattr(secret, "env_dict"):
                env_vars.update(secret.env_dict)

        provider.create_sandbox_pod(
            pod_name, image_uri, timeout,
            gpu=gpu, cpu=cpu, memory=memory,
            env_vars=env_vars if env_vars else None,
        )
        return Sandbox(pod_name, provider)

    class _CreateWithAio:
        def __call__(self, *args, **kwargs):
            return Sandbox._do_create(*args, **kwargs)

        async def aio(self, *args, **kwargs):
            return await asyncio.to_thread(Sandbox._do_create, *args, **kwargs)

    create = _CreateWithAio()

    @property
    def exec(self):
        def fn(*args: str, workdir: str | None = None, secrets: Collection[Any] | None = None, timeout: int | None = None, **kwargs) -> ContainerProcess:
            env = {}
            for secret in (secrets or []):
                if hasattr(secret, "env_dict"):
                    env.update(secret.env_dict)
            return self._provider.exec_in_pod(self._pod_name, *args, workdir=workdir, env=env or None)

        async def aio(*args, **kwargs):
            return await asyncio.to_thread(fn, *args, **kwargs)

        fn.aio = aio
        return fn

    @property
    def mkdir(self):
        def fn(path: str, parents: bool = False):
            flag = "-p " if parents else ""
            self.exec("bash", "-c", f"mkdir {flag}{path}")

        async def aio(path, parents=False):
            return await asyncio.to_thread(fn, path, parents)

        fn.aio = aio
        return fn

    @property
    def terminate(self):
        def fn():
            self._provider.delete_instance(self._pod_name)

        async def aio():
            return await asyncio.to_thread(fn)

        fn.aio = aio
        return fn

    @property
    def wait(self):
        def fn(*, raise_on_termination: bool = True):
            pass

        async def aio(*, raise_on_termination: bool = True):
            pass

        fn.aio = aio
        return fn
