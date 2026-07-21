import boto3
import botocore.exceptions

from src.utils.config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET,
    R2_QUARANTINE_BUCKET,
    R2_PUBLIC_URL,
)

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    return _s3


def generate_quarantine_put(object_key: str, content_type: str, expires_in: int = 900) -> str:
    return _get_s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": R2_QUARANTINE_BUCKET, "Key": object_key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def generate_quarantine_get(object_key: str, expires_in: int = 300) -> str:
    return _get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": R2_QUARANTINE_BUCKET, "Key": object_key},
        ExpiresIn=expires_in,
    )


def head_quarantine(object_key: str) -> dict | None:
    try:
        resp = _get_s3().head_object(Bucket=R2_QUARANTINE_BUCKET, Key=object_key)
    except botocore.exceptions.ClientError:
        return None
    return {"size": resp["ContentLength"], "content_type": resp.get("ContentType", "")}


def copy_to_public(object_key: str) -> None:
    _get_s3().copy_object(
        Bucket=R2_BUCKET,
        Key=object_key,
        CopySource={"Bucket": R2_QUARANTINE_BUCKET, "Key": object_key},
    )


def delete_quarantine(object_key: str) -> None:
    try:
        _get_s3().delete_object(Bucket=R2_QUARANTINE_BUCKET, Key=object_key)
    except botocore.exceptions.ClientError:
        pass


def delete_public(object_key: str) -> None:
    try:
        _get_s3().delete_object(Bucket=R2_BUCKET, Key=object_key)
    except botocore.exceptions.ClientError:
        pass


def public_url_for(object_key: str) -> str:
    return f"{R2_PUBLIC_URL}/{object_key}"
