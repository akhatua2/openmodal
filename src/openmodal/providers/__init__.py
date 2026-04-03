"""Provider factory — returns the appropriate cloud provider based on config."""

from __future__ import annotations


def get_provider(spec=None, *, sandbox: bool = False):
    import os
    from openmodal.function import FunctionSpec

    override = os.environ.get("OPENMODAL_PROVIDER")
    if override:
        backend = override
    elif sandbox:
        backend = "gke"
    elif spec and isinstance(spec, FunctionSpec) and spec.gpu and (spec.web_server_port or spec.volumes):
        backend = "gke"
    else:
        backend = "gce"

    if backend == "local":
        from openmodal.providers.local import get_provider as _get
        return _get()
    elif backend == "gke":
        from openmodal.providers.gcp.gke import get_provider as _get
        return _get()
    else:
        from openmodal.providers.gcp.compute import get_provider as _get
        return _get()
