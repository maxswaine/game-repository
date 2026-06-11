from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from src.models.enums.comment_type_enum import CommentTypeEnum
from src.models.user_models.user import UserPublicRead


class CommentCreate(BaseModel):
    body: str = Field(..., max_length=1000)
    comment_type: CommentTypeEnum = CommentTypeEnum.general


class CommentRead(BaseModel):
    id: str
    game_id: str
    user: UserPublicRead
    body: str
    comment_type: CommentTypeEnum
    likes: int
    liked_by_me: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
