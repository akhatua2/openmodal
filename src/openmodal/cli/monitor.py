"""openmodal monitor — live resource utilization dashboard."""

from __future__ import annotations

import time

import click


@click.command()
@click.argument("app_name", required=False, default=None)
@click.option("--interval", type=float, default=2.0, help="Refresh interval in seconds.")
def monitor(app_name: str | None, interval: float):
    """Live resource utilization dashboard for OpenModal containers."""
    from rich.console import Console
    from rich.live import Live

    from openmodal.monitor.collector import MetricsCollector
    from openmodal.monitor.dashboard import Dashboard
    from openmodal.monitor.history import MetricsHistory
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
        click.echo("\nUsage: openmodal monitor <name>")
        return

    instances = provider.list_instances(app_name)
    if not instances:
        # No running pod — try showing saved history
        history = MetricsHistory.load(app_name)
        if history and history.get_all():
            snapshots = history.get_all()
            has_gpu = any(s.gpu_util is not None for s in snapshots)
            dashboard = Dashboard(history, app_name, has_gpu=has_gpu)
            Console().print(dashboard.render())
            return
        raise click.ClickException(
            f"No containers found matching '{app_name}' and no saved metrics. "
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

    pod_name = target["name"]
    status = target.get("status", "").lower()

    # Completed pod — show saved history
    if status in ("succeeded", "failed", "exited"):
        history = MetricsHistory.load(pod_name)
        if history is None:
            raise click.ClickException(
                f"Container '{pod_name}' has finished and no saved metrics found."
            )
        snapshots = history.get_all()
        has_gpu = any(s.gpu_util is not None for s in snapshots)
        dashboard = Dashboard(history, pod_name, has_gpu=has_gpu)
        Console().print(dashboard.render())
        return

    # Live monitoring — load existing history if available
    history = MetricsHistory.load(pod_name) or MetricsHistory()
    collector = MetricsCollector(provider, pod_name, history, interval=interval)
    collector.start()

    try:
        dashboard = Dashboard(history, pod_name)
        with Live(dashboard.render(), refresh_per_second=1) as live:
            while not collector.stopped:
                dashboard.has_gpu = collector.has_gpu
                live.update(dashboard.render())
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()
        click.echo(f"\nMetrics saved to ~/.openmodal/metrics/{pod_name}.json", err=True)
