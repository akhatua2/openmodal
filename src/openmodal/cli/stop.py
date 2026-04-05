"""openmodal stop — delete containers and cron jobs for an app."""

from __future__ import annotations

import click

from openmodal.providers import get_provider as _get_provider


@click.command()
@click.argument("app_name")
@click.argument("func_name", required=False, default=None)
def stop(app_name: str, func_name: str | None):
    """Stop (delete) containers and cron jobs for an app."""
    provider = _get_provider()
    if func_name:
        name = provider.instance_name(app_name, func_name)
        provider.delete_instance(name)
        try:
            provider.delete_cron_job(f"{name}-cron")
        except NotImplementedError:
            pass
        click.echo(f"Deleted {app_name}/{func_name}")
    else:
        for vm in provider.list_instances(app_name):
            name = vm.get("name", "")
            click.echo(f"  deleting {name}...")
            provider.delete_instance(name)
        try:
            for cj in provider.list_cron_jobs(app_name):
                name = cj.get("name", "")
                click.echo(f"  deleting cron job {name}...")
                provider.delete_cron_job(name)
        except NotImplementedError:
            pass
        click.echo(f"Stopped all containers for {app_name}")
