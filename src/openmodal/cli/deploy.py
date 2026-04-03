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
        if spec.web_server_port and spec.source_file:
            image = spec.image.with_web_server(spec.source_file, spec.name)
        else:
            image = spec.image
        image_uri = image.build_and_push(app.name)
        click.echo(f"  image: {image_uri}")

        click.echo(f"  creating container ({spec.gpu})...")
        spec._app_name = app.name
        provider = _get_provider(spec)
        _, ip = provider.create_instance(spec, image_uri)
        port = spec.web_server_port or 8000
        url = f"http://{ip}:{port}"

        click.echo(f"  waiting for healthy (timeout: {spec.web_server_startup_timeout}s)...")
        if not provider.wait_for_healthy(ip, port, timeout=spec.web_server_startup_timeout):
            raise click.ClickException(f"Server failed to start within {spec.web_server_startup_timeout}s")

        click.echo(f"\n  {func_name} => {url}")

    click.echo("\ndeploy complete.")
