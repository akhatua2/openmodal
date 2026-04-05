"""openmodal ps — list running containers and cron jobs."""

from __future__ import annotations

import click


@click.command()
@click.argument("app_name", required=False, default=None)
def ps(app_name: str | None):
    """List running OpenModal containers and cron jobs."""
    from openmodal.providers import get_provider as _get_provider

    provider = _get_provider()
    instances = provider.list_instances(app_name)

    has_output = False

    if instances:
        has_output = True
        click.echo(f"{'NAME':<45} {'STATUS':<12} {'IP'}")
        for inst in instances:
            click.echo(f"{inst.get('name', ''):<45} {inst.get('status', ''):<12} {inst.get('ip', '')}")

    try:
        cron_jobs = provider.list_cron_jobs(app_name)
        if cron_jobs:
            has_output = True
            click.echo(f"\n{'CRON JOB':<35} {'SCHEDULE':<20} {'STATUS':<12} {'LAST RUN'}")
            for cj in cron_jobs:
                click.echo(
                    f"{cj.get('name', ''):<35} "
                    f"{cj.get('schedule', ''):<20} "
                    f"{cj.get('status', ''):<12} "
                    f"{cj.get('last_run', '')}"
                )
    except NotImplementedError:
        pass

    if not has_output:
        click.echo("No running containers or cron jobs.")
