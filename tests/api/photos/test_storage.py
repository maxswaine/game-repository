from unittest.mock import MagicMock, patch

import botocore.exceptions

from src.services import storage


def test_generate_quarantine_put_calls_presign():
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://presigned-put"
    with patch("src.services.storage._get_s3", return_value=s3), \
         patch("src.services.storage.R2_QUARANTINE_BUCKET", "quarantine"):
        url = storage.generate_quarantine_put("games/g/a.jpg", "image/jpeg")
    assert url == "https://presigned-put"
    args, kwargs = s3.generate_presigned_url.call_args
    assert args[0] == "put_object"
    assert kwargs["Params"]["Bucket"] == "quarantine"
    assert kwargs["Params"]["Key"] == "games/g/a.jpg"
    assert kwargs["Params"]["ContentType"] == "image/jpeg"


def test_head_quarantine_returns_size_and_type():
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 1234, "ContentType": "image/png"}
    with patch("src.services.storage._get_s3", return_value=s3):
        info = storage.head_quarantine("games/g/a.png")
    assert info == {"size": 1234, "content_type": "image/png"}


def test_head_quarantine_returns_none_when_missing():
    s3 = MagicMock()
    s3.head_object.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )
    with patch("src.services.storage._get_s3", return_value=s3):
        assert storage.head_quarantine("games/g/missing.png") is None


def test_copy_to_public_copies_between_buckets():
    s3 = MagicMock()
    with patch("src.services.storage._get_s3", return_value=s3), \
         patch("src.services.storage.R2_QUARANTINE_BUCKET", "quarantine"), \
         patch("src.services.storage.R2_BUCKET", "public"):
        storage.copy_to_public("games/g/a.jpg")
    _, kwargs = s3.copy_object.call_args
    assert kwargs["Bucket"] == "public"
    assert kwargs["Key"] == "games/g/a.jpg"
    assert kwargs["CopySource"] == {"Bucket": "quarantine", "Key": "games/g/a.jpg"}


def test_public_url_for():
    with patch("src.services.storage.R2_PUBLIC_URL", "https://cdn.example.com"):
        assert storage.public_url_for("games/g/a.jpg") == "https://cdn.example.com/games/g/a.jpg"
