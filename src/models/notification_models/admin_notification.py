from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class AdminNotificationRequest(BaseModel):
    target: Literal["user", "broadcast"]
    user_id: Optional[str] = None
    game_id: Optional[str] = None
    title: str
    body: str

    @model_validator(mode="after")
    def check_user_id_present_for_user_target(self):
        if self.target == "user" and not self.user_id:
            raise ValueError("user_id is required when target is 'user'")
        return self
