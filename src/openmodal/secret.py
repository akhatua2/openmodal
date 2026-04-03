"""Secrets — injected as environment variables into remote containers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SECRETS_DIR = Path.home() / ".openmodal" / "secrets"


@dataclass
class Secret:
    name: str
    required_keys: list[str] = field(default_factory=list)
    _env: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_name(cls, name: str, *, required_keys: list[str] | None = None) -> Secret:
        """Load a secret by name from ~/.openmodal/secrets/.

        Create secrets with: openmodal secret create <name> KEY=VALUE
        """
        secret_file = SECRETS_DIR / f"{name}.json"
        env = {}
        if secret_file.exists():
            env = json.loads(secret_file.read_text())
        return cls(name=name, required_keys=required_keys or [], _env=env)

    @classmethod
    def from_dict(cls, env: dict[str, str]) -> Secret:
        return cls(name="", _env=env)

    @property
    def env_dict(self) -> dict[str, str]:
        return dict(self._env)
