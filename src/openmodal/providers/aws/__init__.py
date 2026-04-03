"""AWS EKS provider — runs everything on AWS using EKS + Karpenter."""

from openmodal.providers.aws.eks import EKSProvider


_provider: EKSProvider | None = None


def get_provider() -> EKSProvider:
    global _provider
    if _provider is None:
        _provider = EKSProvider()
    return _provider
