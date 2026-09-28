import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import require_admin
from src.db.database import get_db
from src.db.tables import Game, GameVideo, User
from src.models.game_models.game_video import (
    VideoUploadUrlRequest,
    VideoUploadUrlResponse,
    VideoRegisterRequest,
    GameVideoRead,
)
from src.services import storage

router = APIRouter()

MAX_VIDEO_BYTES = 50 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/webm"}
EXT_MAP = {"video/mp4": "mp4", "video/webm": "webm"}


def _get_game_or_404(db: Session, game_id: str) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/games/{game_id}/videos/upload-url", response_model=VideoUploadUrlResponse)
def create_upload_url(
    game_id: str,
    request: VideoUploadUrlRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(require_admin),
):
    game = _get_game_or_404(db, game_id)
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported video type")

    ext = EXT_MAP[request.content_type]
    object_key = f"games/{game.id}/videos/{uuid.uuid4().hex}.{ext}"
    upload_url = storage.generate_quarantine_put(object_key, request.content_type)
    return VideoUploadUrlResponse(upload_url=upload_url, object_key=object_key)


@router.post("/games/{game_id}/videos", response_model=GameVideoRead)
def register_video(
    game_id: str,
    request: VideoRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(require_admin),
):
    game = _get_game_or_404(db, game_id)
    object_key = request.object_key

    if not object_key.startswith(f"games/{game.id}/videos/"):
        raise HTTPException(status_code=422, detail="Invalid object key")

    info = storage.head_quarantine(object_key)
    if info is None:
        raise HTTPException(status_code=422, detail="Upload not found")
    if info["size"] > MAX_VIDEO_BYTES:
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Video too large (max 50MB)")

    storage.copy_to_public(object_key)
    storage.delete_quarantine(object_key)

    video = GameVideo(
        game_id=game.id,
        object_key=object_key,
        public_url=storage.public_url_for(object_key),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return GameVideoRead.model_validate(video)


@router.delete("/games/{game_id}/videos/{video_id}", status_code=204)
def delete_video(
    game_id: str,
    video_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(require_admin),
):
    game = _get_game_or_404(db, game_id)
    video = (
        db.query(GameVideo)
        .filter(GameVideo.id == video_id, GameVideo.game_id == game.id)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    storage.delete_public(video.object_key)
    db.delete(video)
    db.commit()
    return None
