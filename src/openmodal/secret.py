"""Secrets — injected as environment variables into remote containers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Secret:
    name: str
    required_keys: list[str] = field(default_factory=list)
    _env: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_name(cls, name: str, *, required_keys: list[str] | None = None) -> Secret:
        return cls(name=name, required_keys=required_keys or [])

    @classmethod
    def from_dict(cls, env: dict[str, str]) -> Secret:
        return cls(name="", _env=env)

    @property
    def env_dict(self) -> dict[str, str]:
        return dict(self._env)
