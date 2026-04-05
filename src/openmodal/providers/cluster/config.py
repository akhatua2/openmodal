"""Cluster provider configuration — reads from ~/.openmodal/cluster.json."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".openmodal" / "cluster.json"


def load_config() -> dict:
    """Load cluster config. Raises RuntimeError if not configured."""
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            "Cluster provider not configured.\n"
            "Run: openmodal setup cluster"
        )
    return json.loads(CONFIG_PATH.read_text())


def save_config(config: dict) -> None:
    """Save cluster config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def get_nodes() -> list[str]:
    return load_config()["nodes"]


def get_default_node() -> str:
    cfg = load_config()
    return cfg.get("default_node", cfg["nodes"][0])


def get_remote_base() -> str:
    return load_config()["remote_base"]


def get_env_setup_script() -> str | None:
    return load_config().get("env_setup_script")
