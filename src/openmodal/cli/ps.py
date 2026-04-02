"""openmodal ps — list running containers."""

from __future__ import annotations

import click

from openmodal.providers.gcp.compute import get_provider


@click.command()
@click.argument("app_name", required=False, default=None)
def ps(app_name: str | None):
    """List running OpenModal containers."""
    provider = get_provider()
    vms = provider.list_instances(app_name)
    if not vms:
        click.echo("No running containers.")
        return

    click.echo(f"{'NAME':<45} {'STATUS':<12} {'IP':<18} {'ZONE'}")
    for vm in vms:
        name = vm.get("name", "")
        status = vm.get("status", "")
        ip = (vm.get("networkInterfaces", [{}])[0]
              .get("accessConfigs", [{}])[0]
              .get("natIP", ""))
        zone = vm.get("zone", "").rsplit("/", 1)[-1]
        click.echo(f"{name:<45} {status:<12} {ip:<18} {zone}")
