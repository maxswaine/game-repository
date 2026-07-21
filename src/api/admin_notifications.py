from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import require_admin
from src.db.database import SessionLocal, get_db
from src.db.tables import User
from src.models.notification_models.admin_notification import AdminNotificationRequest
from src.services import notifications

router = APIRouter()


def _broadcast_task(title: str, body: str, game_id: str | None) -> None:
    db = SessionLocal()
    try:
        data = {"game_id": game_id} if game_id else None
        user_ids = [row.id for row in db.query(User.id).filter(User.is_active.is_(True)).all()]
        for user_id in user_ids:
            notifications.send(db, user_id, title, body, notification_type="custom", data=data)
        db.commit()
    finally:
        db.close()


@router.post("/notifications")
def send_admin_notification(
        db: Annotated[Session, Depends(get_db)],
        body: AdminNotificationRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(require_admin),
):
    data = {"game_id": body.game_id} if body.game_id else None

    if body.target == "user":
        target_user = db.query(User).filter(User.id == body.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        notifications.send(db, body.user_id, body.title, body.body, notification_type="custom", data=data)
        db.commit()
        return JSONResponse(status_code=200, content={"status": "sent"})

    background_tasks.add_task(_broadcast_task, body.title, body.body, body.game_id)
    return JSONResponse(status_code=202, content={"status": "queued"})
