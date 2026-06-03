from sqlalchemy.orm import Session

from src.db.tables import UserAchievement
from src.models.enums.achievement_enum import AchievementTypeEnum


def grant_if_not_exists(db: Session, user_id: str, achievement: AchievementTypeEnum) -> bool:
    existing = db.query(UserAchievement).filter_by(
        user_id=user_id, achievement_type=achievement.value
    ).first()
    if existing:
        return False
    db.add(UserAchievement(user_id=user_id, achievement_type=achievement.value))
    return True
