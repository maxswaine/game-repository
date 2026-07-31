import re

from pydantic import BaseModel, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailingListSubscribe(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v


class MailingListSubscribeResponse(BaseModel):
    status: str
