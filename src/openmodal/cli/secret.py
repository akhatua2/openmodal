"""openmodal secret — create and manage secrets."""

from __future__ import annotations

import json
from pathlib import Path

import click

SECRETS_DIR = Path.home() / ".openmodal" / "secrets"


@click.group()
def secret():
    """Manage secrets for OpenModal containers."""


@secret.command("create")
@click.argument("name")
@click.argument("values", nargs=-1, required=True)
def create(name: str, values: tuple[str, ...]):
    """Create a named secret from key=value pairs.

    Example: openmodal secret create wandb-secret WANDB_API_KEY=abc123
    """
    env = {}
    for v in values:
        if "=" not in v:
            raise click.ClickException(f"Invalid format: '{v}'. Use KEY=VALUE.")
        key, _, value = v.partition("=")
        env[key] = value

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    (SECRETS_DIR / f"{name}.json").write_text(json.dumps(env))
    click.echo(f"Secret '{name}' created with keys: {', '.join(env.keys())}")


@secret.command("list")
def list_secrets():
    """List all saved secrets."""
    if not SECRETS_DIR.exists():
        click.echo("No secrets found.")
        return
    for f in sorted(SECRETS_DIR.glob("*.json")):
        data = json.loads(f.read_text())
        keys = ", ".join(data.keys())
        click.echo(f"  {f.stem}: {keys}")


@secret.command("delete")
@click.argument("name")
def delete(name: str):
    """Delete a secret."""
    path = SECRETS_DIR / f"{name}.json"
    if not path.exists():
        raise click.ClickException(f"Secret '{name}' not found.")
    path.unlink()
    click.echo(f"Secret '{name}' deleted.")
