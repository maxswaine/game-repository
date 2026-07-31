from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user, require_admin
from src.db.database import get_db
from src.db.tables import Feedback
from src.models.feedback_models.feedback import FeedbackAdminRead, FeedbackCreate, FeedbackResponse

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
    db.commit()
    db.refresh(feedback)
    return FeedbackResponse(id=feedback.id, created_at=feedback.created_at)


@admin_router.get("/feedback", response_model=List[FeedbackAdminRead])
def list_feedback(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .all()
    )
