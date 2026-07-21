import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import Game, GamePhoto, User
from src.models.game_models.game_photo import (
    PhotoUploadUrlRequest,
    PhotoUploadUrlResponse,
    PhotoRegisterRequest,
    PhotoReorderRequest,
    GamePhotoRead,
)
from src.services import storage
from src.services.moderation import check_image

router = APIRouter()

MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def auth_required():
    return Depends(get_current_active_user)


def _owned_game_or_error(db: Session, game_id: str, user: User) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.contributor_id != user.id:
        raise HTTPException(status_code=403, detail="Not your game")
    return game


def _photo_count(db: Session, game_id: str) -> int:
    return db.query(GamePhoto).filter(GamePhoto.game_id == game_id).count()


def _resync_cover(db: Session, game: Game) -> None:
    # Flush pending position/photo changes first: the session runs with
    # autoflush=False, so without this the ordered query below would read
    # stale positions and pick the wrong cover.
    db.flush()
    photos = (
        db.query(GamePhoto)
        .filter(GamePhoto.game_id == game.id)
        .order_by(GamePhoto.position)
        .all()
    )
    game.image_url = photos[0].public_url if photos else None


@router.post("/{game_id}/photos/upload-url", response_model=PhotoUploadUrlResponse)
def create_upload_url(
    game_id: str,
    request: PhotoUploadUrlRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    game = _owned_game_or_error(db, game_id, current_user)
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")
    if _photo_count(db, game.id) >= MAX_PHOTOS:
        raise HTTPException(status_code=409, detail="Photo limit reached (max 10)")

    ext = EXT_MAP[request.content_type]
    object_key = f"games/{game.id}/{uuid.uuid4().hex}.{ext}"
    upload_url = storage.generate_quarantine_put(object_key, request.content_type)
    return PhotoUploadUrlResponse(upload_url=upload_url, object_key=object_key)


@router.post("/{game_id}/photos", response_model=GamePhotoRead)
def register_photo(
    game_id: str,
    request: PhotoRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    game = _owned_game_or_error(db, game_id, current_user)
    object_key = request.object_key

    if not object_key.startswith(f"games/{game.id}/"):
        raise HTTPException(status_code=422, detail="Invalid object key")

    count = _photo_count(db, game.id)
    if count >= MAX_PHOTOS:
        raise HTTPException(status_code=409, detail="Photo limit reached (max 10)")

    info = storage.head_quarantine(object_key)
    if info is None:
        raise HTTPException(status_code=422, detail="Upload not found")
    if info["size"] > MAX_PHOTO_BYTES:
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Photo too large (max 5MB)")

    get_url = storage.generate_quarantine_get(object_key)
    if not check_image(get_url):
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Image violates community guidelines.")

    storage.copy_to_public(object_key)
    storage.delete_quarantine(object_key)

    photo = GamePhoto(
        game_id=game.id,
        object_key=object_key,
        public_url=storage.public_url_for(object_key),
        position=count,
    )
    db.add(photo)
    db.flush()
    _resync_cover(db, game)
    db.commit()
    db.refresh(photo)
    return GamePhotoRead.model_validate(photo)


@router.delete("/{game_id}/photos/{photo_id}", status_code=204)
def delete_photo(
    game_id: str,
    photo_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    game = _owned_game_or_error(db, game_id, current_user)
    photo = (
        db.query(GamePhoto)
        .filter(GamePhoto.id == photo_id, GamePhoto.game_id == game.id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    storage.delete_public(photo.object_key)
    db.delete(photo)
    db.flush()

    remaining = (
        db.query(GamePhoto)
        .filter(GamePhoto.game_id == game.id)
        .order_by(GamePhoto.position)
        .all()
    )
    for index, item in enumerate(remaining):
        item.position = index
    _resync_cover(db, game)
    db.commit()
    return None


@router.patch("/{game_id}/photos/order", response_model=list[GamePhotoRead])
def reorder_photos(
    game_id: str,
    request: PhotoReorderRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    game = _owned_game_or_error(db, game_id, current_user)
    photos = db.query(GamePhoto).filter(GamePhoto.game_id == game.id).all()
    by_id = {p.id: p for p in photos}

    if set(request.photo_ids) != set(by_id.keys()):
        raise HTTPException(status_code=422, detail="photo_ids must match the game's photos exactly")

    for index, pid in enumerate(request.photo_ids):
        by_id[pid].position = index
    _resync_cover(db, game)
    db.commit()

    ordered = (
        db.query(GamePhoto)
        .filter(GamePhoto.game_id == game.id)
        .order_by(GamePhoto.position)
        .all()
    )
    return [GamePhotoRead.model_validate(p) for p in ordered]
