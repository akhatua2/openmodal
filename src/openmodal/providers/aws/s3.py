"""S3 bucket operations for volumes."""

from __future__ import annotations

import logging

logger = logging.getLogger("openmodal.aws.s3")


def ensure_bucket(bucket_name: str, region: str):
    """Create an S3 bucket if it doesn't exist."""
    import boto3
    s3 = boto3.client("s3", region_name=region)
    try:
        s3.head_bucket(Bucket=bucket_name)
    except Exception:
        logger.debug(f"Creating S3 bucket: {bucket_name}")
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
