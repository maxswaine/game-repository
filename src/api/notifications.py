from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import Notification, User

router = APIRouter()


@router.post("/{notification_id}/opened", status_code=200,
             responses={404: {"description": "Notification not found"}})
def mark_notification_opened(
        db: Annotated[Session, Depends(get_db)],
        notification_id: str,
        current_user: User = Depends(get_current_active_user),
):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.opened_at is None:
        notification.opened_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok"}
