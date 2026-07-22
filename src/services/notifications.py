import json
import logging
import uuid
from typing import Optional

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushTicketError,
)
from sqlalchemy.orm import Session

from src.db.tables import Notification, PushDeliveryTicket, PushToken
from src.models.enums.achievement_enum import AchievementTypeEnum

logger = logging.getLogger(__name__)

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

    # Registration validates format now, but rows created before that check existed may
    # still be malformed. exponent_server_sdk builds the whole batch payload up front
    # (PushMessage.get_payload() raises ValueError for a bad token) — one bad token in
    # the list used to fail EVERY token for this user, including healthy devices.
    valid_tokens, invalid_tokens = [], []
    for t in tokens:
        (valid_tokens if PushClient.is_exponent_push_token(t.token) else invalid_tokens).append(t)

    for t in invalid_tokens:
        logger.warning("Pruning malformed push token for user %s: %r", user_id, t.token)
        db.query(PushToken).filter(PushToken.token == t.token).delete()

    if not valid_tokens:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")
        return

    messages = [
        PushMessage(to=t.token, title=title, body=body, data=data or {})
        for t in valid_tokens
    ]

    note = _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")

    try:
        tickets = _get_push_client().publish_multiple(messages)
    except Exception:
        logger.exception("Expo publish_multiple failed for user %s", user_id)
        for t in valid_tokens:
            db.add(PushDeliveryTicket(
                notification_id=note.id,
                token=t.token,
                status="failed",
                error_message="publish_multiple raised — see server logs",
            ))
        return

    any_ok = False
    for ticket in tickets:
        token = ticket.push_message.to
        try:
            ticket.validate_response()
        except DeviceNotRegisteredError:
            db.query(PushToken).filter(PushToken.token == token).delete()
            db.add(PushDeliveryTicket(
                notification_id=note.id, token=token, status="failed", error_message="DeviceNotRegistered",
            ))
            continue
        except PushTicketError as e:
            db.add(PushDeliveryTicket(
                notification_id=note.id, token=token, status="failed", error_message=str(e),
            ))
            continue

        any_ok = True
        db.add(PushDeliveryTicket(
            notification_id=note.id, token=token, ticket_id=ticket.id, status="pending",
        ))

    note.status = "sent" if any_ok else "failed"


def _log(db, user_id, title, body, notification_type, data, achievement_type, status) -> Notification:
    note = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
        achievement_type=achievement_type,
        status=status,
    )
    db.add(note)
    return note


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
