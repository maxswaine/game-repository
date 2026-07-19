import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_target_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise ValueError("target_url must start with http:// or https://")
    return value


class ShortLinkCreate(BaseModel):
    code: str
    target_url: str
    label: Optional[str] = None

    @field_validator("code")
    @classmethod
    def code_url_safe(cls, value: str) -> str:
        if not CODE_PATTERN.match(value):
            raise ValueError("code must match ^[a-zA-Z0-9_-]+$")
        return value

    @field_validator("target_url")
    @classmethod
    def target_url_scheme(cls, value: str) -> str:
        return _validate_target_url(value)


class ShortLinkPatch(BaseModel):
    target_url: Optional[str] = None
    label: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("target_url")
    @classmethod
    def target_url_scheme(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_target_url(value)


class ShortLinkRead(BaseModel):
    code: str
    target_url: str
    label: Optional[str] = None
    is_active: bool
    scan_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
