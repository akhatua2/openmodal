"""CLI entry point."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import click

from openmodal.app import App


def load_app(app_path: str) -> App:
    path = Path(app_path).resolve()
    if not path.exists():
        raise click.ClickException(f"File not found: {app_path}")

    spec = importlib.util.spec_from_file_location("_user_app", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_user_app"] = module
    spec.loader.exec_module(module)

    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, App):
            return obj

    raise click.ClickException(f"No openmodal.App found in {app_path}")


@click.group()
@click.option("-v", "--verbose", is_flag=True)
@click.option("--local", is_flag=True, help="Run on local Docker instead of cloud.")
@click.option("--aws", is_flag=True, help="Run on AWS EKS.")
def cli(verbose: bool, local: bool, aws: bool):
    import os
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )
    if local:
        os.environ["OPENMODAL_PROVIDER"] = "local"
    elif aws:
        os.environ["OPENMODAL_PROVIDER"] = "eks"


from openmodal.cli.deploy import deploy  # noqa: E402
from openmodal.cli.run import run  # noqa: E402
from openmodal.cli.stop import stop  # noqa: E402
from openmodal.cli.ps import ps  # noqa: E402

cli.add_command(deploy)
cli.add_command(run)
cli.add_command(stop)
cli.add_command(ps)


def main():
    cli()
