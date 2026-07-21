from typing import Annotated

from fastapi import APIRouter, Depends
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
    existing = db.query(PushToken).filter(PushToken.token == body.token).first()
    if existing:
        existing.user_id = current_user.id
        existing.platform = body.platform
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
