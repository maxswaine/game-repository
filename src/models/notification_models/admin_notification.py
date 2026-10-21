from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class AdminNotificationRequest(BaseModel):
    target: Literal["user", "broadcast"]
    user_id: Optional[str] = None
    game_id: Optional[str] = None
    title: str
    body: str
    # Broadcast reach. Anonymous devices have no user row, so they are invisible to the
    # "users" sweep. Defaults to "users" — the behaviour before device rows existed — so an
    # existing admin client's broadcast reaches exactly who it did before.
    audience: Literal["users", "devices", "all"] = "users"

    @model_validator(mode="after")
    def check_user_id_present_for_user_target(self):
        if self.target == "user" and not self.user_id:
            raise ValueError("user_id is required when target is 'user'")
        return self
