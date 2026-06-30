from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import Feedback
from src.models.feedback_models.feedback import FeedbackCreate, FeedbackResponse

router = APIRouter()


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
