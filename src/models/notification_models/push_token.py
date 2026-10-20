from typing import Optional

from pydantic import BaseModel


class PushTokenCreate(BaseModel):
    token: str
    platform: str
    # Optional so app builds <= 1.1.2, which send only {token, platform}, keep working.
    device_id: Optional[str] = None


class PushTokenDelete(BaseModel):
    token: str
