from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from src.api.users import get_current_active_user, require_admin
from src.db.database import get_db
from src.db.tables import Feedback
from src.models.enums.achievement_enum import AchievementTypeEnum
from src.models.feedback_models.feedback import FeedbackAdminRead, FeedbackCreate, FeedbackResponse
from src.services.achievements import grant_if_not_exists

router = APIRouter()
admin_router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    feedback = Feedback(
        user_id=current_user.id,
        type=body.type.value,
        message=body.message,
    )
    db.add(feedback)
    grant_if_not_exists(db, current_user.id, AchievementTypeEnum.GIVE_FEEDBACK)
    db.commit()
    db.refresh(feedback)
    return FeedbackResponse(id=feedback.id, created_at=feedback.created_at)


@admin_router.get("/feedback", response_model=List[FeedbackAdminRead])
def list_feedback(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    items = (
        db.query(Feedback)
        .options(joinedload(Feedback.user))
        .order_by(Feedback.created_at.desc())
        .all()
    )
    return [
        FeedbackAdminRead(
            id=f.id,
            user_id=f.user_id,
            username=f.user.username if f.user else "",
            type=f.type,
            message=f.message,
            status=f.status,
            created_at=f.created_at,
        )
        for f in items
    ]
