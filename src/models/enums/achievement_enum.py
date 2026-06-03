from enum import Enum


class AchievementTypeEnum(str, Enum):
    FIRST_LIKE = "first_like"
    FIRST_SUBMIT = "first_submit"
    SHARE_GAME = "share_game"
    FIVE_UPLOADS = "five_uploads"
    TEN_LIKES_ON_UPLOAD = "ten_likes_on_upload"
    GIVE_FEEDBACK = "give_feedback"
    COMPLETE_TUTORIAL = "complete_tutorial"


SIGNAL_ONLY_ACHIEVEMENTS = {
    AchievementTypeEnum.SHARE_GAME,
    AchievementTypeEnum.GIVE_FEEDBACK,
    AchievementTypeEnum.COMPLETE_TUTORIAL,
}
