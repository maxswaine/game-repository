from typing import Optional

from pydantic import BaseModel, model_validator


class PushTokenCreate(BaseModel):
    token: str
    platform: str
    # Optional so app builds <= 1.1.2, which send only {token, platform}, keep working.
    device_id: Optional[str] = None
    # IANA zone name from the phone (e.g. "Europe/London"), so campaigns land at a sensible local
    # hour. Optional so older builds keep working; unrecognised names are dropped, not rejected,
    # because failing registration over a timezone would cost us the push token.
    timezone: Optional[str] = None


class PushTokenDelete(BaseModel):
    # Either identifier removes the row. `token` stays optional rather than required because
    # a device whose notifications were revoked in OS settings can no longer produce one —
    # getExpoPushTokenAsync throws without permission — while device_id is in the keychain and
    # always readable. Without this, revoked devices could never unsubscribe and kept counting
    # as reachable. Builds that send only {token} are unaffected.
    token: Optional[str] = None
    device_id: Optional[str] = None

    @model_validator(mode="after")
    def require_an_identifier(self):
        if not self.token and not self.device_id:
            raise ValueError("token or device_id is required")
        return self
