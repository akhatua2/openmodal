"""Provider factory — returns the appropriate cloud provider based on config."""

from __future__ import annotations


def get_provider(spec=None, *, sandbox: bool = False):
    import os

    override = os.environ.get("OPENMODAL_PROVIDER")
    backend = override or "gke"

    if backend == "local":
        from openmodal.providers.local import get_provider as _get
        return _get()
    elif backend == "aws":
        from openmodal.providers.aws import get_provider as _get
        return _get()
    elif backend == "azure":
        from openmodal.providers.azure import get_provider as _get
        return _get()
    else:
        from openmodal.providers.gcp.gke import get_provider as _get
        return _get()
