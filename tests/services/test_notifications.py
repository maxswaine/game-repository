import uuid
from unittest.mock import MagicMock, patch

from exponent_server_sdk import DeviceNotRegisteredError

from src.db.tables import Notification, PushToken
from src.models.enums.achievement_enum import AchievementTypeEnum, SIGNAL_ONLY_ACHIEVEMENTS
from src.services import notifications


class TestPushTokenSchema:
    def test_round_trip(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        fetched = db.query(PushToken).filter_by(token="ExponentPushToken[abc]").first()
        assert fetched is not None
        assert fetched.user_id == test_user.id
        assert fetched.platform == "ios"
        assert fetched.updated_at is not None


class TestNotificationSchema:
    def test_round_trip(self, db, test_user):
        note = Notification(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            type="custom",
            title="Hello",
            body="World",
            data=None,
            achievement_type=None,
            status="sent",
        )
        db.add(note)
        db.commit()

        fetched = db.query(Notification).filter_by(id=note.id).first()
        assert fetched is not None
        assert fetched.status == "sent"
        assert fetched.created_at is not None


class TestHallOfFameEnum:
    def test_is_a_valid_achievement_type(self):
        assert AchievementTypeEnum.HALL_OF_FAME.value == "hall_of_fame"

    def test_not_signal_only(self):
        assert AchievementTypeEnum.HALL_OF_FAME not in SIGNAL_ONLY_ACHIEVEMENTS


class TestSendNoToken:
    def test_writes_no_token_status_and_never_touches_expo(self, db, test_user):
        with patch("src.services.notifications._get_push_client") as mock_get_client:
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        mock_get_client.assert_not_called()
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "no_token"
        assert note.title == "Title"
        assert note.body == "Body"
        assert note.type == "custom"


class TestSendSuccess:
    def test_writes_sent_status_and_calls_expo_with_data(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_ticket = MagicMock()
        mock_ticket.validate_response.return_value = None
        mock_client = MagicMock()
        mock_client.publish_multiple.return_value = [mock_ticket]

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body", data={"game_id": "g1"})
            db.commit()

        mock_client.publish_multiple.assert_called_once()
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "sent"
        assert note.data == '{"game_id": "g1"}'


class TestSendFailure:
    def test_writes_failed_status_when_expo_call_raises(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_client = MagicMock()
        mock_client.publish_multiple.side_effect = RuntimeError("network down")

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "failed"


class TestSendPrunesDeadToken:
    def test_deletes_token_on_device_not_registered_but_still_logs_sent(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[dead]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_ticket = MagicMock()
        mock_ticket.push_message.to = "ExponentPushToken[dead]"
        mock_ticket.validate_response.side_effect = DeviceNotRegisteredError(mock_ticket)
        mock_client = MagicMock()
        mock_client.publish_multiple.return_value = [mock_ticket]

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        assert db.query(PushToken).filter_by(token="ExponentPushToken[dead]").first() is None
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "sent"


class TestSendAchievementNotification:
    def test_uses_copy_for_known_achievement_type_and_tags_data(self, db, test_user):
        with patch("src.services.notifications.send") as mock_send:
            notifications.send_achievement_notification(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[:2] == (db, test_user.id)
        assert kwargs["notification_type"] == "achievement"
        assert kwargs["achievement_type"] == "first_like"
        assert kwargs["data"] == {"achievement_type": "first_like"}
        assert isinstance(kwargs.get("title") or args[2], str)

    def test_falls_back_to_generic_copy_for_hall_of_fame(self, db, test_user):
        with patch("src.services.notifications.send") as mock_send:
            notifications.send_achievement_notification(db, test_user.id, AchievementTypeEnum.HALL_OF_FAME)

        _, kwargs = mock_send.call_args
        assert kwargs["achievement_type"] == "hall_of_fame"
