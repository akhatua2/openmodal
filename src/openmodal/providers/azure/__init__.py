"""Azure AKS provider — runs everything on Azure using AKS."""

from openmodal.providers.azure.aks import AKSProvider


_provider: AKSProvider | None = None


def get_provider() -> AKSProvider:
    global _provider
    if _provider is None:
        _provider = AKSProvider()
    return _provider
