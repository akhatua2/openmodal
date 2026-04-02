"""openmodal ps — list running containers."""

from __future__ import annotations

import click


@click.command()
@click.argument("app_name", required=False, default=None)
def ps(app_name: str | None):
    """List running OpenModal containers."""
    from openmodal.remote import _get_provider

    provider = _get_provider()
    instances = provider.list_instances(app_name)
    if not instances:
        click.echo("No running containers.")
        return

    click.echo(f"{'NAME':<45} {'STATUS':<12} {'IP'}")
    for inst in instances:
        click.echo(f"{inst.get('name', ''):<45} {inst.get('status', ''):<12} {inst.get('ip', '')}")
