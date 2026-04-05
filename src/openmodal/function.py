"""Function specification — captured config for a deployed function."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class FunctionSpec:
    func: Callable
    name: str
    image: Any = None
    gpu: str = ""
    cpu: float | None = None
    memory: int | None = None
    scaledown_window: int = 300
    timeout: int = 600
    secrets: list[Any] = field(default_factory=list)
    retries: int = 0
    volumes: dict[str, Any] = field(default_factory=dict)
    max_concurrent_inputs: int = 1
    web_server_port: int | None = None
    web_server_startup_timeout: int = 600
    web_url: str | None = None
    schedule: Any = None  # Cron | Period | None
    source_file: str | None = None
    module_name: str | None = None
    qualname: str | None = None
    _app_name: str = ""
