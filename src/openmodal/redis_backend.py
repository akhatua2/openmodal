"""Redis backend — lazy singleton that deploys and connects to Redis via providers."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger("openmodal.redis")

REDIS_PORT = 6379

_lock = threading.Lock()
_redis_client = None
_redis_deployed = False
_redis_url: str | None = None
_port_forward_proc = None


def _get_redis_client():
    """Return a connected redis.Redis client, deploying Redis if needed."""
    global _redis_client, _redis_deployed, _redis_url

    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    with _lock:
        if _redis_client is not None:
            return _redis_client

        import redis

        # Inside a remote container — connect via env var
        url = os.environ.get("OPENMODAL_REDIS_URL")
        if url:
            _redis_client = redis.Redis.from_url(url, decode_responses=False)
            _redis_client.ping()
            return _redis_client

        # Client side — deploy Redis via provider
        from openmodal.providers import get_provider
        provider = get_provider()
        _redis_url = provider.ensure_redis()
        _redis_deployed = True

        # For K8s providers, the client runs outside the cluster,
        # so we port-forward to reach the Redis pod
        provider_type = type(provider).__name__
        if provider_type != "LocalProvider":
            _start_port_forward()
            client_url = f"redis://localhost:{REDIS_PORT}"
        else:
            client_url = _redis_url

        _redis_client = redis.Redis.from_url(client_url, decode_responses=False)
        _wait_for_ready(_redis_client)
        return _redis_client


def _start_port_forward():
    global _port_forward_proc
    _port_forward_proc = subprocess.Popen(
        ["kubectl", "port-forward", "pod/openmodal-redis",
         f"{REDIS_PORT}:{REDIS_PORT}", "-n", "default"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(2)


def _wait_for_ready(client, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            client.ping()
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError("Redis did not become ready")


def get_redis_url_for_container() -> str | None:
    """Return the Redis URL that remote containers should use, or None if not deployed."""
    if not _redis_deployed:
        return None
    return _redis_url


def shutdown_redis():
    """Delete the Redis pod/container."""
    global _redis_client, _redis_deployed, _redis_url, _port_forward_proc
    if not _redis_deployed:
        return

    if _port_forward_proc:
        _port_forward_proc.terminate()
        _port_forward_proc.wait()
        _port_forward_proc = None

    from openmodal.providers import get_provider
    provider = get_provider()
    provider.delete_redis()

    _redis_client = None
    _redis_deployed = False
    _redis_url = None
