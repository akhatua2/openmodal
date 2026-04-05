"""Cluster provider — runs on bare-metal SSH clusters."""

from openmodal.providers.cluster.cluster import ClusterProvider

_provider: ClusterProvider | None = None


def get_provider() -> ClusterProvider:
    global _provider
    if _provider is None:
        _provider = ClusterProvider()
    return _provider
