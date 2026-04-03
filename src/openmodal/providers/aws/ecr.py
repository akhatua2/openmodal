"""ECR (Elastic Container Registry) operations."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.aws.ecr")


def get_registry_url(account_id: str, region: str, name: str, tag: str) -> str:
    return f"{account_id}.dkr.ecr.{region}.amazonaws.com/{name}:{tag}"


def ensure_repository(account_id: str, region: str, repo_name: str):
    """Create ECR repository if it doesn't exist."""
    import boto3
    ecr = boto3.client("ecr", region_name=region)
    try:
        ecr.describe_repositories(repositoryNames=[repo_name])
    except ecr.exceptions.RepositoryNotFoundException:
        ecr.create_repository(repositoryName=repo_name)
        logger.debug(f"Created ECR repository: {repo_name}")


def docker_login(account_id: str, region: str):
    """Authenticate local Docker daemon with ECR."""
    registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    token = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", region],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(
        ["docker", "login", "--username", "AWS", "--password-stdin", registry],
        input=token, capture_output=True, text=True, check=True,
    )
