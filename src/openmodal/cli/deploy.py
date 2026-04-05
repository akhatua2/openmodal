"""openmodal deploy — persistent deployment."""

from __future__ import annotations

import click

from openmodal.cli import load_app
from openmodal.providers import get_provider as _get_provider


@click.command()
@click.argument("app_path")
def deploy(app_path: str):
    """Deploy an app. Containers stay up until idle timeout or `openmodal stop`."""
    app = load_app(app_path)
    click.echo(f"openmodal deploy: {app.name}")

    for func_name, spec in app.functions.items():
        click.echo(f"\n  function: {func_name}")
        if spec.image is None:
            raise click.ClickException(f"No image defined for {func_name}")

        click.echo("  building image...")
        if spec.schedule and spec.source_file:
            image = spec.image.with_cron_runner(spec.source_file, spec.name)
        elif spec.web_server_port and spec.source_file:
            image = spec.image.with_web_server(spec.source_file, spec.name)
        else:
            image = spec.image
        image_uri = image.build_and_push(app.name)
        click.echo(f"  image: {image_uri}")

        spec._app_name = app.name
        provider = _get_provider(spec)

        if spec.schedule:
            cron_schedule = spec.schedule.to_k8s_schedule()
            click.echo(f"  creating cron job (schedule: {cron_schedule})...")
            cron_name = provider.create_cron_job(
                spec, image_uri,
                f"{provider.instance_name(app.name, func_name)}-cron",
            )
            click.echo(f"\n  {func_name} => CronJob '{cron_name}' (schedule: {cron_schedule})")
        else:
            click.echo(f"  creating container ({spec.gpu})...")
            _, ip = provider.create_instance(spec, image_uri)
            port = spec.web_server_port or 8000
            url = f"http://{ip}:{port}"

            click.echo(f"  waiting for healthy (timeout: {spec.web_server_startup_timeout}s)...")
            if not provider.wait_for_healthy(ip, port, timeout=spec.web_server_startup_timeout):
                raise click.ClickException(f"Server failed to start within {spec.web_server_startup_timeout}s")

            click.echo(f"\n  {func_name} => {url}")

    click.echo("\ndeploy complete.")
