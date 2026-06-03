from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import User, UserAchievement
from src.models.achievement_models.achievement import AchievementRead, AchievementSignalRequest
from src.models.enums.achievement_enum import AchievementTypeEnum, SIGNAL_ONLY_ACHIEVEMENTS
from src.services.achievements import grant_if_not_exists

router = APIRouter()

_ALL_ACHIEVEMENTS = list(AchievementTypeEnum)


@router.get("/", response_model=List[AchievementRead])
def get_achievements(
        db: Annotated[Session, Depends(get_db)],
        current_user: User = Depends(get_current_active_user),
):
    achieved = {
        row.achievement_type: row.achieved_at
        for row in db.query(UserAchievement).filter_by(user_id=current_user.id).all()
    }
    return [
        AchievementRead(
            achievement_type=achievement,
            achieved=achievement.value in achieved,
            achieved_at=achieved.get(achievement.value),
        )
        for achievement in _ALL_ACHIEVEMENTS
    ]


@router.post("/signal", response_model=AchievementRead, status_code=201)
def signal_achievement(
        payload: AchievementSignalRequest,
        db: Annotated[Session, Depends(get_db)],
        current_user: User = Depends(get_current_active_user),
):
    if payload.achievement_type not in SIGNAL_ONLY_ACHIEVEMENTS:
        raise HTTPException(status_code=400, detail="Achievement cannot be granted via signal")

    grant_if_not_exists(db, current_user.id, payload.achievement_type)
    db.commit()

    row = db.query(UserAchievement).filter_by(
        user_id=current_user.id,
        achievement_type=payload.achievement_type.value,
    ).first()

    return AchievementRead(
        achievement_type=payload.achievement_type,
        achieved=True,
        achieved_at=row.achieved_at,
    )
