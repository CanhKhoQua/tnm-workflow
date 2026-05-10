from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def r2_configured(config) -> bool:
    return all([
        config.r2_account_id,
        config.r2_access_key_id,
        config.r2_secret_access_key,
        config.r2_bucket_name,
        config.r2_public_url,
    ])


def upload_report(html_path: str, config) -> str:
    """Upload an HTML report to Cloudflare R2. Returns the public URL."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    filename = Path(html_path).name
    key = f"reports/{filename}"

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{config.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=config.r2_access_key_id,
            aws_secret_access_key=config.r2_secret_access_key,
            region_name="auto",
        )
        s3.upload_file(
            html_path,
            config.r2_bucket_name,
            key,
            ExtraArgs={"ContentType": "text/html; charset=utf-8"},
        )
        public_url = f"{config.r2_public_url.rstrip('/')}/{key}"
        logger.info("Uploaded to R2: %s", public_url)
        return public_url
    except (BotoCoreError, ClientError) as e:
        logger.error("R2 upload failed: %s", e)
        raise
