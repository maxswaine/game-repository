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
from src.models.enums.game_rejection_reason_enum import GameRejectionReasonEnum

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
    if not user_id:
        # Now that push_tokens.user_id is nullable this is a live footgun, not a nicety:
        # `PushToken.user_id == None` renders as `IS NULL`, so a caller that lost its user_id
        # would deliver one person's achievement or comment reply to EVERY signed-out device.
        # Drop the send and leave a line to find it by; no caller should ever reach here.
        logger.error(
            "notifications.send called with no user_id (type=%s, title=%r) — dropped. "
            "Use send_to_anonymous_devices() for device broadcasts.",
            notification_type, title,
        )
        return

    tokens = db.query(PushToken).filter(PushToken.user_id == user_id).all()
    _send_to_tokens(db, tokens, user_id, title, body, notification_type, data, achievement_type)


def send_to_anonymous_devices(
    db: Session,
    title: str,
    body: str,
    *,
    notification_type: str = "custom",
    data: Optional[dict] = None,
) -> None:
    """Broadcast to devices that registered a push token without ever signing in.

    One Notification row covers the whole batch (user_id NULL — there is no user to attribute
    it to); the per-device trace is the PushDeliveryTicket rows keyed on token. Only
    broadcasts belong here: achievements, comment replies and review outcomes all need a user.
    """
    tokens = db.query(PushToken).filter(PushToken.user_id.is_(None)).all()
    _send_to_tokens(db, tokens, None, title, body, notification_type, data, None)


def _send_to_tokens(
    db: Session,
    tokens: list,
    user_id: Optional[str],
    title: str,
    body: str,
    notification_type: str,
    data: Optional[dict],
    achievement_type: Optional[str],
) -> None:
    audience = f"user {user_id}" if user_id else "anonymous devices"

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
        logger.warning("Pruning malformed push token for %s: %r", audience, t.token)
        db.query(PushToken).filter(PushToken.token == t.token).delete()

    if not valid_tokens:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")
        return

    note = _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")

    payload_data = {**(data or {}), "notification_id": note.id}
    messages = [
        PushMessage(to=t.token, title=title, body=body, data=payload_data)
        for t in valid_tokens
    ]

    try:
        tickets = _get_push_client().publish_multiple(messages)
    except Exception:
        logger.exception("Expo publish_multiple failed for %s", audience)
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


def send_game_status_notification(
    db: Session,
    user_id: str,
    game_id: str,
    game_name: str,
    status: str,
    rejection_reason_code: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> None:
    if status == "approved":
        title = "Game approved!"
        body = f'"{game_name}" is now live.'
    elif rejection_reason_code == GameRejectionReasonEnum.duplicate.value:
        # A duplicate has nothing for the contributor to edit, so the generic
        # "edit and resubmit" copy below would send them looking for a fix that isn't there.
        title = "We've got this one!"
        body = f'"{game_name}" is already on the app - tap to see our note, we\'d love your rule variants.'
    else:
        title = "Nearly there!"
        body = f'Your game "{game_name}" needs a few tweaks before it goes live. Check out our comments on the app, edit and resubmit!'

    send(
        db,
        user_id,
        title,
        body,
        notification_type="game_status_change",
        data={"game_id": game_id, "status": status},
    )


_COMMENT_SNIPPET_LIMIT = 120


def send_new_comment_notification(
    db: Session,
    user_id: str,
    game_id: str,
    game_name: str,
    commenter_username: str,
    comment_type: str,
    comment_body: str,
) -> None:
    if comment_type == "rule_variant":
        title = "New rule variant"
        body = f'{commenter_username} added a rule variant to "{game_name}".'
    else:
        title = "New comment"
        snippet = comment_body if len(comment_body) <= _COMMENT_SNIPPET_LIMIT \
            else comment_body[:_COMMENT_SNIPPET_LIMIT - 3] + "..."
        body = f'{commenter_username} on "{game_name}": {snippet}'

    send(
        db,
        user_id,
        title,
        body,
        notification_type="new_comment",
        data={"game_id": game_id},
    )


def notify_admins_new_pending_game(
    db: Session,
    game_id: str,
    game_name: str,
    contributor_username: str,
) -> None:
    from src.db.tables import User
    from src.models.enums.role_enum import Role

    admin_ids = [
        row.id for row in
        db.query(User.id).filter(User.role == Role.admin, User.is_active.is_(True)).all()
    ]
    title = "New game pending review"
    body = f'"{game_name}" was submitted by {contributor_username} and needs review.'
    for admin_id in admin_ids:
        send(
            db,
            admin_id,
            title,
            body,
            notification_type="admin_pending_review",
            data={"game_id": game_id},
        )
