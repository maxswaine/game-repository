from datetime import datetime, timezone
from typing import Annotated

from exponent_server_sdk import PushClient
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import get_current_user_optional
from src.db.database import get_db
from src.db.tables import PushToken, User
from src.models.notification_models.push_token import PushTokenCreate, PushTokenDelete

router = APIRouter()


@router.post("/")
def register_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenCreate,
        current_user: Annotated[User | None, Depends(get_current_user_optional)],
):
    # Auth is optional: the app asks for push permission straight after the tutorial, before
    # the user has an account. Those registrations used to 401 and vanish, so a signed-out
    # device had notifications switched on at the OS level and no row here.
    if not PushClient.is_exponent_push_token(body.token):
        raise HTTPException(status_code=400, detail="Not a valid Expo push token")

    if body.device_id:
        # One row per device. The Expo token is the primary key, so a rotated token would
        # otherwise leave the device's old row behind and audience="all" would reach it twice.
        db.query(PushToken).filter(
            PushToken.device_id == body.device_id,
            PushToken.token != body.token,
        ).delete()

    existing = db.query(PushToken).filter(PushToken.token == body.token).first()
    if existing:
        if current_user:
            # Claim on sign-in: an anonymous row becomes this user's, and a re-register by
            # the owner is a no-op. An *anonymous* re-register of an already-claimed token
            # deliberately leaves user_id alone — losing the owner would downgrade a
            # signed-in device to broadcast-only.
            existing.user_id = current_user.id
        existing.platform = body.platform
        if body.device_id:
            existing.device_id = body.device_id
        # The app re-registers on every launch, but user_id/platform are almost always
        # unchanged — SQLAlchemy then emits no UPDATE and `onupdate` never fires, leaving
        # updated_at frozen at first registration. Stamp it explicitly so the column means
        # "last launch with notifications still granted" and stale tokens are visible.
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return JSONResponse(status_code=200, content={"status": "ok"})

    db.add(PushToken(
        token=body.token,
        user_id=current_user.id if current_user else None,
        device_id=body.device_id,
        platform=body.platform,
    ))
    db.commit()
    return JSONResponse(status_code=201, content={"status": "ok"})


@router.delete("/", status_code=204)
def delete_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenDelete,
        current_user: Annotated[User | None, Depends(get_current_user_optional)],
):
    # The row is deleted rather than re-anonymised: the app calls this both for sign-out and
    # for the Settings notifications toggle, and the backend cannot tell them apart. Nulling
    # user_id would leave a user who explicitly turned notifications off still receiving
    # broadcasts. The cost is that signing out drops the device's anonymous subscription;
    # the next launch re-registers it.
    # Match on either identifier. A revoked device can only supply device_id, and OR-ing them
    # also clears the device's row when its Expo token has rotated since registration.
    identifiers = []
    if body.token:
        identifiers.append(PushToken.token == body.token)
    if body.device_id:
        identifiers.append(PushToken.device_id == body.device_id)

    # An unauthenticated caller can only drop a row no user has claimed.
    deletable = PushToken.user_id.is_(None)
    if current_user:
        deletable = deletable | (PushToken.user_id == current_user.id)

    db.query(PushToken).filter(or_(*identifiers), deletable).delete()
    db.commit()
