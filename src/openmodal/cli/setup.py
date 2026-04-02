"""openmodal setup — one-time infrastructure setup."""

from __future__ import annotations

import click


@click.command()
@click.option("--provider", default="gke", type=click.Choice(["gke"]))
@click.option("--gpu", multiple=True, default=["l4"], help="GPU types to provision (l4, a100-80gb, h100)")
@click.option("--teardown", is_flag=True, help="Tear down the cluster instead of creating it")
def setup(provider: str, gpu: tuple[str, ...], teardown: bool):
    """Set up cloud infrastructure (one-time)."""
    if provider == "gke":
        from openmodal.providers.gcp.gke_setup import setup_cluster, teardown_cluster

        if teardown:
            click.echo("Tearing down GKE cluster...")
            teardown_cluster()
            click.echo("Done.")
        else:
            click.echo(f"Setting up GKE cluster with GPU types: {', '.join(gpu)}")
            setup_cluster(gpu_types=list(gpu))
            click.echo("Done. Set OPENMODAL_PROVIDER=gke to use it.")
