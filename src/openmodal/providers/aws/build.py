"""Docker image building via AWS CodeBuild (remote). No local Docker needed."""

from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from pathlib import Path

import boto3

from openmodal.providers.aws.config import CLUSTER_NAME

logger = logging.getLogger("openmodal.aws.build")

PROJECT_NAME = f"{CLUSTER_NAME}-image-builder"
BUCKET_NAME_PREFIX = f"{CLUSTER_NAME}-build"

BUILDSPEC = """version: 0.2
phases:
  pre_build:
    commands:
      - >-
        aws ecr get-login-password --region $AWS_DEFAULT_REGION |
        docker login --username AWS --password-stdin $ECR_REGISTRY
  build:
    commands:
      - docker build -t $IMAGE_URI .
  post_build:
    commands:
      - docker push $IMAGE_URI
"""


def _get_bucket_name(account_id: str, region: str) -> str:
    return f"{BUCKET_NAME_PREFIX}-{account_id}-{region}"


def _ensure_bucket(account_id: str, region: str) -> str:
    """Create S3 bucket for build context if it doesn't exist."""
    s3 = boto3.client("s3", region_name=region)
    bucket = _get_bucket_name(account_id, region)
    try:
        s3.head_bucket(Bucket=bucket)
    except s3.exceptions.ClientError:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
        logger.debug(f"Created S3 bucket: {bucket}")
    return bucket


def _ensure_codebuild_role(account_id: str, region: str) -> str:
    """Create IAM role for CodeBuild if it doesn't exist. Returns role ARN."""
    iam = boto3.client("iam")
    role_name = f"{CLUSTER_NAME}-codebuild-role"
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        iam.get_role(RoleName=role_name)
        return role_arn
    except iam.exceptions.NoSuchEntityException:
        pass

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "codebuild.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
    )

    # Attach permissions for ECR push, S3 read, and CloudWatch Logs
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:GetObjectVersion"],
                "Resource": f"arn:aws:s3:::{_get_bucket_name(account_id, region)}/*",
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                "Resource": f"arn:aws:s3:::{_get_bucket_name(account_id, region)}",
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": "*",
            },
        ],
    }

    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="codebuild-permissions",
        PolicyDocument=json.dumps(policy),
    )

    # IAM role propagation takes a few seconds
    time.sleep(10)
    logger.debug(f"Created CodeBuild IAM role: {role_name}")
    return role_arn


def _ensure_codebuild_project(account_id: str, region: str) -> str:
    """Create CodeBuild project if it doesn't exist."""
    cb = boto3.client("codebuild", region_name=region)

    try:
        cb.batch_get_projects(names=[PROJECT_NAME])
        projects = cb.batch_get_projects(names=[PROJECT_NAME])["projects"]
        if projects:
            return PROJECT_NAME
    except Exception:
        pass

    bucket = _ensure_bucket(account_id, region)
    role_arn = _ensure_codebuild_role(account_id, region)

    cb.create_project(
        name=PROJECT_NAME,
        source={
            "type": "S3",
            "location": f"{bucket}/context.zip",
            "buildspec": BUILDSPEC,
        },
        artifacts={"type": "NO_ARTIFACTS"},
        environment={
            "type": "LINUX_CONTAINER",
            "image": "aws/codebuild/standard:7.0",
            "computeType": "BUILD_GENERAL1_MEDIUM",
            "privilegedMode": True,
        },
        serviceRole=role_arn,
    )
    logger.debug(f"Created CodeBuild project: {PROJECT_NAME}")
    return PROJECT_NAME


def _zip_context(context_dir: str) -> bytes:
    """Zip a build context directory into bytes."""
    buf = io.BytesIO()
    context_path = Path(context_dir)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in context_path.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(context_path))
    return buf.getvalue()


def codebuild(context_dir: str, image_uri: str, account_id: str, region: str):
    """Build a Docker image remotely using AWS CodeBuild and push to ECR."""
    logger.debug(f"CodeBuild: {image_uri}")

    _ensure_codebuild_project(account_id, region)
    bucket = _ensure_bucket(account_id, region)

    # Upload build context to S3
    s3 = boto3.client("s3", region_name=region)
    context_zip = _zip_context(context_dir)
    s3.put_object(Bucket=bucket, Key="context.zip", Body=context_zip)

    # Start build
    ecr_registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    cb = boto3.client("codebuild", region_name=region)
    build = cb.start_build(
        projectName=PROJECT_NAME,
        environmentVariablesOverride=[
            {"name": "IMAGE_URI", "value": image_uri, "type": "PLAINTEXT"},
            {"name": "ECR_REGISTRY", "value": ecr_registry, "type": "PLAINTEXT"},
        ],
    )
    build_id = build["build"]["id"]
    logger.debug(f"Started build: {build_id}")

    # Poll until complete
    while True:
        resp = cb.batch_get_builds(ids=[build_id])
        status = resp["builds"][0]["buildStatus"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "FAULT", "STOPPED", "TIMED_OUT"):
            phase = resp["builds"][0].get("phases", [])
            raise RuntimeError(f"CodeBuild failed ({status}): {phase}")
        time.sleep(5)

    logger.debug(f"Built: {image_uri}")
