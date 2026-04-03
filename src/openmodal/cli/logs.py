"""openmodal logs — view container logs."""

from __future__ import annotations

import re

import click


def _validate_since(ctx, param, value):
    if value is None:
        return value
    if not re.match(r"^\d+[smh]$", value):
        raise click.BadParameter("Must be a duration like '30s', '5m', or '1h'.")
    return value


@click.command()
@click.argument("app_name", required=False, default=None)
@click.option("-f", "--follow/--no-follow", default=True, help="Follow log output (default: true).")
@click.option("--tail", type=int, default=None, help="Number of recent lines to show.")
@click.option("--since", type=str, default=None, callback=_validate_since,
              help="Show logs since duration (e.g. 5m, 1h).")
def logs(app_name: str | None, follow: bool, tail: int | None, since: str | None):
    """View logs from OpenModal containers.

    If APP_NAME is omitted, lists available containers.
    """
    from openmodal.providers import get_provider

    provider = get_provider()

    if app_name is None:
        instances = provider.list_instances()
        if not instances:
            click.echo("No containers found. Deploy with: openmodal deploy <app.py>")
            return
        click.echo("Available containers:\n")
        click.echo(f"  {'NAME':<45} {'STATUS':<12}")
        for inst in instances:
            click.echo(f"  {inst['name']:<45} {inst.get('status', ''):<12}")
        click.echo("\nUsage: openmodal logs <name>")
        return

    instances = provider.list_instances(app_name)
    if not instances:
        raise click.ClickException(
            f"No containers found matching '{app_name}'. "
            f"Run 'openmodal ps' to see running containers."
        )

    if len(instances) > 1:
        click.echo(f"Multiple containers match '{app_name}':\n", err=True)
        for i, inst in enumerate(instances, 1):
            click.echo(f"  [{i}] {inst['name']}  ({inst.get('status', '')})", err=True)
        click.echo(err=True)
        choice = click.prompt("Select container", type=int, default=1, err=True)
        if choice < 1 or choice > len(instances):
            raise click.ClickException("Invalid selection.")
        target = instances[choice - 1]
    else:
        target = instances[0]

    instance_name = target["name"]
    status = target.get("status", "").lower()

    if follow and status in ("succeeded", "failed", "exited"):
        click.echo(
            f"Container '{instance_name}' has status '{status}'. "
            f"Showing existing logs (--no-follow).",
            err=True,
        )
        follow = False

    click.echo(f"Streaming logs from {instance_name}...", err=True)

    proc = provider.stream_logs(
        instance_name,
        follow=follow,
        tail=tail,
        since=since,
        include_stderr=True,
    )

    if proc is None:
        raise click.ClickException(
            f"Failed to stream logs from '{instance_name}'. "
            f"Check that the container exists and you have access."
        )

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        click.echo("\nStopped.", err=True)
