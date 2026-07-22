import logging
from datetime import datetime, timedelta, timezone

from exponent_server_sdk import DeviceNotRegisteredError, PushTicket, PushTicketError
from sqlalchemy.orm import Session

from src.db.tables import PushDeliveryTicket, PushToken
from src.services.notifications import _get_push_client

logger = logging.getLogger(__name__)

# Expo recommends waiting before checking receipts so delivery has time to happen.
MIN_AGE_MINUTES = 15
# Receipts aren't guaranteed to stay available forever; give up past this age.
MAX_AGE_HOURS = 24


def check_pending_deliveries(db: Session) -> None:
    now = datetime.now(timezone.utc)
    ready_by = now - timedelta(minutes=MIN_AGE_MINUTES)
    expired_before = now - timedelta(hours=MAX_AGE_HOURS)

    expired = db.query(PushDeliveryTicket).filter(
        PushDeliveryTicket.status == "pending",
        PushDeliveryTicket.created_at < expired_before,
    ).all()
    for row in expired:
        row.status = "unknown"
        row.checked_at = now

    due = db.query(PushDeliveryTicket).filter(
        PushDeliveryTicket.status == "pending",
        PushDeliveryTicket.created_at <= ready_by,
        PushDeliveryTicket.created_at >= expired_before,
    ).all()
    if not due:
        return

    rows_by_ticket_id = {row.ticket_id: row for row in due}
    fake_tickets = [
        PushTicket(push_message=None, status=None, message=None, details=None, id=ticket_id)
        for ticket_id in rows_by_ticket_id
    ]

    try:
        receipts = _get_push_client().check_receipts_multiple(fake_tickets)
    except Exception:
        logger.exception("Expo check_receipts_multiple failed")
        return

    for receipt in receipts:
        row = rows_by_ticket_id.get(receipt.id)
        if row is None:
            continue

        row.checked_at = now
        try:
            receipt.validate_response()
            row.status = "delivered"
        except DeviceNotRegisteredError:
            row.status = "failed"
            row.error_message = "DeviceNotRegistered"
            db.query(PushToken).filter(PushToken.token == row.token).delete()
        except PushTicketError as e:
            row.status = "failed"
            row.error_message = str(e)
