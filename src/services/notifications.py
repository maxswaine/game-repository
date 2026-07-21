import json
import uuid
from typing import Optional

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushTicketError,
)
from sqlalchemy.orm import Session

from src.db.tables import Notification, PushToken
from src.models.enums.achievement_enum import AchievementTypeEnum

_push_client: Optional[PushClient] = None


def _get_push_client() -> PushClient:
    global _push_client
    if _push_client is None:
        _push_client = PushClient()
    return _push_client


def send(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    *,
    notification_type: str = "custom",
    data: Optional[dict] = None,
    achievement_type: Optional[str] = None,
) -> None:
    tokens = db.query(PushToken).filter(PushToken.user_id == user_id).all()

    if not tokens:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="no_token")
        return

    messages = [
        PushMessage(to=t.token, title=title, body=body, data=data or {})
        for t in tokens
    ]

    try:
        tickets = _get_push_client().publish_multiple(messages)
    except Exception:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")
        return

    for ticket in tickets:
        try:
            ticket.validate_response()
        except DeviceNotRegisteredError:
            db.query(PushToken).filter(PushToken.token == ticket.push_message.to).delete()
        except PushTicketError:
            pass

    _log(db, user_id, title, body, notification_type, data, achievement_type, status="sent")


def _log(db, user_id, title, body, notification_type, data, achievement_type, status) -> None:
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
        achievement_type=achievement_type,
        status=status,
    ))


ACHIEVEMENT_COPY: dict[AchievementTypeEnum, tuple[str, str]] = {
    AchievementTypeEnum.FIRST_LIKE: ("Achievement unlocked!", "You liked your first game."),
    AchievementTypeEnum.FIRST_SUBMIT: ("Achievement unlocked!", "You submitted your first game."),
    AchievementTypeEnum.FIVE_UPLOADS: ("Achievement unlocked!", "You've uploaded 5 games."),
    AchievementTypeEnum.TEN_LIKES_ON_UPLOAD: ("Achievement unlocked!", "One of your games hit 10 likes."),
    AchievementTypeEnum.HALL_OF_FAME: ("Hall of Fame!", "Your game has been verified by What's That Game."),
}

_DEFAULT_ACHIEVEMENT_COPY = ("Achievement unlocked!", "You've earned a new achievement.")


def send_achievement_notification(db: Session, user_id: str, achievement_type: AchievementTypeEnum) -> None:
    title, body = ACHIEVEMENT_COPY.get(achievement_type, _DEFAULT_ACHIEVEMENT_COPY)
    send(
        db,
        user_id,
        title,
        body,
        notification_type="achievement",
        data={"achievement_type": achievement_type.value},
        achievement_type=achievement_type.value,
    )
