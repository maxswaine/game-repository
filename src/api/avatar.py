import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import User
from src.models.user_models.avatar import (
    AvatarUploadUrlRequest,
    AvatarUploadUrlResponse,
    AvatarRegisterRequest,
)
from src.models.user_models.user import UserPrivateRead
from src.services import storage
from src.services.moderation import check_image
from src.utils.config import R2_PUBLIC_URL

router = APIRouter()

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def auth_required():
    return Depends(get_current_active_user)


def _delete_if_ours(avatar_url: str | None) -> None:
    if avatar_url and R2_PUBLIC_URL and avatar_url.startswith(R2_PUBLIC_URL):
        old_key = avatar_url[len(R2_PUBLIC_URL) + 1:]
        storage.delete_public(old_key)


@router.post("/me/avatar/upload-url", response_model=AvatarUploadUrlResponse)
def create_avatar_upload_url(
    request: AvatarUploadUrlRequest,
    current_user: User = auth_required(),
):
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")

    ext = EXT_MAP[request.content_type]
    object_key = f"users/{current_user.id}/{uuid.uuid4().hex}.{ext}"
    upload_url = storage.generate_quarantine_put(object_key, request.content_type)
    return AvatarUploadUrlResponse(upload_url=upload_url, object_key=object_key)


@router.post("/me/avatar", response_model=UserPrivateRead)
def register_avatar(
    request: AvatarRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    object_key = request.object_key

    if not object_key.startswith(f"users/{current_user.id}/"):
        raise HTTPException(status_code=422, detail="Invalid object key")

    info = storage.head_quarantine(object_key)
    if info is None:
        raise HTTPException(status_code=422, detail="Upload not found")
    if info["size"] > MAX_AVATAR_BYTES:
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Photo too large (max 5MB)")

    get_url = storage.generate_quarantine_get(object_key)
    if not check_image(get_url):
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Image violates community guidelines.")

    storage.copy_to_public(object_key)
    storage.delete_quarantine(object_key)

    _delete_if_ours(current_user.avatar_url)

    current_user.avatar_url = storage.public_url_for(object_key)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", response_model=UserPrivateRead)
def remove_avatar(
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    _delete_if_ours(current_user.avatar_url)
    current_user.avatar_url = None
    db.commit()
    db.refresh(current_user)
    return current_user
