"""Stacking decorators for function configuration."""

from __future__ import annotations

from collections.abc import Callable


def concurrent(max_inputs: int = 1) -> Callable:
    """Set the maximum number of concurrent requests per container."""
    def decorator(func: Callable) -> Callable:
        func._openmodal_concurrent = max_inputs
        return func
    return decorator


def web_server(port: int, startup_timeout: int = 600) -> Callable:
    """Mark a function as an HTTP server listening on the given port."""
    def decorator(func: Callable) -> Callable:
        func._openmodal_web_server_port = port
        func._openmodal_web_server_startup_timeout = startup_timeout
        return func
    return decorator
