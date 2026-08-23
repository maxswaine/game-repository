from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class FeedbackType(str, Enum):
    bug_report = "Bug Report"
    feature_request = "Feature Request"
    general_feedback = "General Feedback"
    other = "Other"


class FeedbackCreate(BaseModel):
    type: FeedbackType
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message must not be empty")
        if len(v) > 2000:
            raise ValueError("message must not exceed 2000 characters")
        return v


class FeedbackResponse(BaseModel):
    id: str
    created_at: datetime


class FeedbackAdminRead(BaseModel):
    id: str
    user_id: str
    username: str
    type: str
    message: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackResolvePatch(BaseModel):
    action: str  # "acknowledge" | "needs_work"
