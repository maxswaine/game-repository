from unittest.mock import patch

from src.models.enums.achievement_enum import AchievementTypeEnum
from src.services.achievements import grant_if_not_exists


class TestGrantNotificationHook:
    def test_sends_notification_for_non_signal_achievement(self, db, test_user):
        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            granted = grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        assert granted is True
        mock_send.assert_called_once_with(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

    def test_does_not_send_for_signal_only_achievement(self, db, test_user):
        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            grant_if_not_exists(db, test_user.id, AchievementTypeEnum.SHARE_GAME)

        mock_send.assert_not_called()

    def test_does_not_send_when_already_granted(self, db, test_user):
        grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)
        db.commit()

        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            granted_again = grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        assert granted_again is False
        mock_send.assert_not_called()
