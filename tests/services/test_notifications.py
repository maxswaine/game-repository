import uuid

from src.db.tables import Notification, PushToken
from src.models.enums.achievement_enum import AchievementTypeEnum, SIGNAL_ONLY_ACHIEVEMENTS


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
