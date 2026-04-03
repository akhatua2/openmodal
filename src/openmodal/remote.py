"""Remote execution — spins up containers with the agent, sends function calls, returns results."""

from __future__ import annotations

import atexit
import concurrent.futures
import json
import logging
import pickle
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from openmodal.function import FunctionSpec
from openmodal.runtime.agent import DEFAULT_PORT

logger = logging.getLogger("openmodal.remote")

AGENT_PORT = DEFAULT_PORT


def _get_provider(spec: FunctionSpec | None = None):
    from openmodal.providers import get_provider
    return get_provider(spec)


class RemoteExecutor:
    """Manages a remote container running the execution agent."""

    def __init__(self, instance_name: str, ip: str, port: int = AGENT_PORT):
        self.instance_name = instance_name
        self.ip = ip
        self.port = port
        self._base_url = f"http://{ip}:{port}"

    def _start_log_stream(self):
        try:
            from openmodal.providers import get_provider
            provider = get_provider()
            self._log_proc = provider.stream_logs(self.instance_name)
        except Exception:
            self._log_proc = None

    def _stop_log_stream(self):
        if hasattr(self, "_log_proc") and self._log_proc:
            self._log_proc.terminate()
            self._log_proc = None

    def execute(self, spec: FunctionSpec, *args: Any, retries: int = 0, **kwargs: Any) -> Any:
        import os
        last_error: Exception | None = None
        for attempt in range(1 + retries):
            try:
                remote_module = (
                    os.path.basename(spec.source_file).removesuffix(".py")
                    if spec.source_file
                    else spec.module_name
                )
                header = json.dumps({
                    "module": remote_module,
                    "function": spec.name,
                }).encode()
                args_data = pickle.dumps((args, kwargs))
                payload = header + b"\n" + args_data

                self._start_log_stream()

                req = urllib.request.Request(
                    f"{self._base_url}/execute",
                    data=payload,
                    headers={"Content-Type": "application/octet-stream"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=6 * 60 * 60) as resp:
                    result = pickle.loads(resp.read())

                self._stop_log_stream()

                if not result["ok"]:
                    raise RuntimeError(f"Remote execution failed:\n{result['traceback']}")
                return result["result"]
            except Exception as exc:
                self._stop_log_stream()
                last_error = exc
                if attempt < retries:
                    logger.warning(f"Attempt {attempt + 1} failed, retrying ({retries - attempt} left)...")
                    time.sleep(min(2 ** attempt, 30))
        assert last_error is not None
        raise last_error

    def map(self, spec: FunctionSpec, iterable: Any, *, retries: int = 0, max_workers: int = 8) -> Iterator[Any]:
        items = list(iterable)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self.execute, spec, item, retries=retries) for item in items]
            for future in concurrent.futures.as_completed(futures):
                yield future.result()


def _create_agent_instance(app_name: str, func_name: str, spec: FunctionSpec) -> RemoteExecutor:
    """Create a container running the openmodal agent. Returns a connected RemoteExecutor."""
    from openmodal.cli.console import Spinner, fail, success

    provider = _get_provider(spec)
    try:
        provider.preflight_check(spec)
    except RuntimeError as e:
        fail(str(e))
        raise SystemExit(1) from e
    instance_name = app_name.lower().replace("_", "-")
    spec._app_name = app_name

    has_image = spec.image is not None

    if has_image:
        with Spinner("Building image..."):
            agent_image = spec.image.with_agent(AGENT_PORT, source_file=spec.source_file)
            image_uri = agent_image.build_and_push(f"{app_name}-{func_name}-agent")
        success("Image built.")
    else:
        image_uri = None

    spec_label = provider.machine_spec_str(spec.gpu)

    try:
        with Spinner(f"Creating container... ({spec_label})") as spinner:
            _, ip = provider.create_instance(spec, image_uri, name=instance_name)
            elapsed_create = int(spinner.elapsed)
    except (RuntimeError, TimeoutError) as e:
        fail(str(e))
        raise SystemExit(1) from e

    success(f"Container created. ({spec_label} \u2022 {ip} \u2022 {elapsed_create}s)")

    timeout = 600 if has_image else 300
    with Spinner("Starting agent...") as spinner:
        if not provider.wait_for_healthy(ip, AGENT_PORT, timeout=timeout):
            fail(f"Agent on {instance_name} ({ip}) failed to start within {timeout}s")
            raise SystemExit(1)
        elapsed_ready = int(spinner.elapsed)

    success(f"Container ready. ({elapsed_create + elapsed_ready}s total)")

    # Start background metrics collection so `openmodal monitor` has data
    from openmodal.monitor.collector import MetricsCollector
    from openmodal.monitor.history import MetricsHistory
    history = MetricsHistory()
    collector = MetricsCollector(provider, instance_name, history)
    collector.start()
    _collectors[instance_name] = collector

    return RemoteExecutor(instance_name, ip, AGENT_PORT)


_executors: dict[str, RemoteExecutor] = {}
_collectors: dict = {}


def get_executor(app_name: str, func_name: str, spec: FunctionSpec) -> RemoteExecutor:
    key = f"{app_name}/{func_name}"
    if key not in _executors:
        _executors[key] = _create_agent_instance(app_name, func_name, spec)
    return _executors[key]


def shutdown_all():
    # Stop metrics collectors and save history
    for collector in _collectors.values():
        collector.stop()
    _collectors.clear()

    if not _executors:
        return
    from openmodal.cli.console import Spinner, success
    provider = _get_provider()
    with Spinner("Cleaning up containers..."):
        for executor in _executors.values():
            provider.delete_instance(executor.instance_name)
    success("Containers cleaned up.")
    _executors.clear()


atexit.register(shutdown_all)
