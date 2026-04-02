"""Secrets — injected as environment variables into remote containers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Secret:
    name: str
    required_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_name(cls, name: str, *, required_keys: list[str] | None = None) -> Secret:
        return cls(name=name, required_keys=required_keys or [])
