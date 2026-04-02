"""App — groups functions and entrypoints into a deployable unit."""

from __future__ import annotations

import functools
import inspect
import logging
from dataclasses import dataclass
from typing import Callable

from openmodal.function import FunctionSpec
from openmodal.image import Image
from openmodal.secret import Secret
from openmodal.volume import Volume

logger = logging.getLogger("openmodal.app")


@dataclass
class LocalEntrypointSpec:
    func: Callable
    name: str


class App:
    def __init__(self, name: str):
        self.name = name
        self.functions: dict[str, FunctionSpec] = {}
        self.local_entrypoints: dict[str, LocalEntrypointSpec] = {}

    def function(
        self,
        *,
        image: Image | None = None,
        gpu: str = "",
        scaledown_window: int = 300,
        timeout: int = 600,
        secrets: list[Secret] | None = None,
        retries: int = 0,
        volumes: dict[str, Volume] | None = None,
    ):
        def decorator(func: Callable) -> Callable:
            max_concurrent = getattr(func, "_openmodal_concurrent", 1)
            ws_port = getattr(func, "_openmodal_web_server_port", None)
            ws_timeout = getattr(func, "_openmodal_web_server_startup_timeout", timeout)

            source_file = inspect.getfile(func)
            module_name = func.__module__
            qualname = func.__qualname__

            spec = FunctionSpec(
                func=func,
                name=func.__name__,
                image=image,
                gpu=gpu,
                scaledown_window=scaledown_window,
                timeout=timeout,
                secrets=secrets or [],
                retries=retries,
                volumes=volumes or {},
                max_concurrent_inputs=max_concurrent,
                web_server_port=ws_port,
                web_server_startup_timeout=ws_timeout,
                source_file=source_file,
                module_name=module_name,
                qualname=qualname,
            )
            self.functions[func.__name__] = spec

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            wrapper._spec = spec
            wrapper._app = self
            wrapper.web_url = None
            wrapper.local = func

            def _remote(*args, **kwargs):
                from openmodal.remote import get_executor
                executor = get_executor(self.name, func.__name__, spec)
                return executor.execute(spec, *args, retries=spec.retries, **kwargs)

            def _map(iterable, *, max_workers: int = 8):
                from openmodal.remote import get_executor
                executor = get_executor(self.name, func.__name__, spec)
                return executor.map(spec, iterable, retries=spec.retries, max_workers=max_workers)

            wrapper.remote = _remote
            wrapper.map = _map
            return wrapper

        return decorator

    def local_entrypoint(self):
        def decorator(func: Callable) -> Callable:
            self.local_entrypoints[func.__name__] = LocalEntrypointSpec(
                func=func, name=func.__name__,
            )
            return func
        return decorator
