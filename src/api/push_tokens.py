from datetime import datetime, timezone
from typing import Annotated

from exponent_server_sdk import PushClient
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import PushToken, User
from src.models.notification_models.push_token import PushTokenCreate, PushTokenDelete

router = APIRouter()


@router.post("/")
def register_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenCreate,
        current_user: User = Depends(get_current_active_user),
):
    if not PushClient.is_exponent_push_token(body.token):
        raise HTTPException(status_code=400, detail="Not a valid Expo push token")

    existing = db.query(PushToken).filter(PushToken.token == body.token).first()
    if existing:
        existing.user_id = current_user.id
        existing.platform = body.platform
        # The app re-registers on every launch, but user_id/platform are almost always
        # unchanged — SQLAlchemy then emits no UPDATE and `onupdate` never fires, leaving
        # updated_at frozen at first registration. Stamp it explicitly so the column means
        # "last launch with notifications still granted" and stale tokens are visible.
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return JSONResponse(status_code=200, content={"status": "ok"})

    db.add(PushToken(token=body.token, user_id=current_user.id, platform=body.platform))
    db.commit()
    return JSONResponse(status_code=201, content={"status": "ok"})


@router.delete("/", status_code=204)
def delete_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenDelete,
        current_user: User = Depends(get_current_active_user),
):
    db.query(PushToken).filter(
        PushToken.token == body.token,
        PushToken.user_id == current_user.id,
    ).delete()
    db.commit()
