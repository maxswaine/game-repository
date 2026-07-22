import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from exponent_server_sdk import DeviceNotRegisteredError, PushTicketError

from src.db.tables import Notification, PushDeliveryTicket, PushToken
from src.services import receipts


def _make_notification(db, user_id):
    note = Notification(
        id=str(uuid.uuid4()), user_id=user_id, type="custom",
        title="T", body="B", status="sent",
    )
    db.add(note)
    db.flush()
    return note


def _make_pending_ticket(db, notification_id, token, ticket_id, age_minutes):
    row = PushDeliveryTicket(
        id=str(uuid.uuid4()),
        notification_id=notification_id,
        token=token,
        ticket_id=ticket_id,
        status="pending",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )
    db.add(row)
    return row


class TestCheckPendingDeliveries:
    def test_skips_tickets_younger_than_min_age(self, db, test_user):
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=1)
        db.commit()

        mock_client = MagicMock()
        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        mock_client.check_receipts_multiple.assert_not_called()
        assert row.status == "pending"

    def test_marks_delivered_on_ok_receipt(self, db, test_user):
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=20)
        db.commit()

        mock_receipt = MagicMock()
        mock_receipt.id = "ticket-a"
        mock_receipt.validate_response.return_value = None
        mock_client = MagicMock()
        mock_client.check_receipts_multiple.return_value = [mock_receipt]

        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        mock_client.check_receipts_multiple.assert_called_once()
        assert row.status == "delivered"
        assert row.checked_at is not None

    def test_marks_failed_and_prunes_token_on_device_not_registered_receipt(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[a]", user_id=test_user.id, platform="ios"))
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=20)
        db.commit()

        mock_receipt = MagicMock()
        mock_receipt.id = "ticket-a"
        mock_receipt.validate_response.side_effect = DeviceNotRegisteredError(mock_receipt)
        mock_client = MagicMock()
        mock_client.check_receipts_multiple.return_value = [mock_receipt]

        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        assert row.status == "failed"
        assert row.error_message == "DeviceNotRegistered"
        assert db.query(PushToken).filter_by(token="ExponentPushToken[a]").first() is None

    def test_marks_failed_on_other_ticket_error(self, db, test_user):
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=20)
        db.commit()

        mock_receipt = MagicMock()
        mock_receipt.id = "ticket-a"
        mock_receipt.validate_response.side_effect = PushTicketError(mock_receipt)
        mock_client = MagicMock()
        mock_client.check_receipts_multiple.return_value = [mock_receipt]

        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        assert row.status == "failed"

    def test_gives_up_on_tickets_past_max_age_without_calling_expo(self, db, test_user):
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=60 * 25)
        db.commit()

        mock_client = MagicMock()
        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        mock_client.check_receipts_multiple.assert_not_called()
        assert row.status == "unknown"
        assert row.checked_at is not None

    def test_expo_call_raising_leaves_tickets_pending_for_next_poll(self, db, test_user):
        note = _make_notification(db, test_user.id)
        row = _make_pending_ticket(db, note.id, "ExponentPushToken[a]", "ticket-a", age_minutes=20)
        db.commit()

        mock_client = MagicMock()
        mock_client.check_receipts_multiple.side_effect = RuntimeError("network down")

        with patch("src.services.receipts._get_push_client", return_value=mock_client):
            receipts.check_pending_deliveries(db)
            db.commit()

        assert row.status == "pending"
