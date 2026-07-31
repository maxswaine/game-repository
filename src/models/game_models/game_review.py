from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.models.enums.game_rejection_reason_enum import GameRejectionReasonEnum


class GameReviewPatch(BaseModel):
    status: str  # "approved" | "rejected"
    rejection_reason_code: Optional[GameRejectionReasonEnum] = None
    rejection_reason: Optional[str] = None  # optional free-text detail


class GameReportAdminRead(BaseModel):
    id: str
    game_id: str
    game_name: str
    reporter_id: str
    reason: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GameReportResolvePatch(BaseModel):
    action: str  # "dismiss" | "reject"
    rejection_reason_code: Optional[GameRejectionReasonEnum] = None
    reason: Optional[str] = None  # optional free-text detail
