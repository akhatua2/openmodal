"""Function specification — captured config for a deployed function."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from openmodal.image import Image
    from openmodal.secret import Secret
    from openmodal.volume import Volume


@dataclass
class FunctionSpec:
    func: Callable
    name: str
    image: Any = None
    gpu: str = ""
    scaledown_window: int = 300
    timeout: int = 600
    secrets: list[Any] = field(default_factory=list)
    retries: int = 0
    volumes: dict[str, Any] = field(default_factory=dict)
    max_concurrent_inputs: int = 1
    web_server_port: int | None = None
    web_server_startup_timeout: int = 600
    web_url: str | None = None
    source_file: str | None = None
    module_name: str | None = None
    qualname: str | None = None
