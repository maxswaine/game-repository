import json
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ScheduledStatus = Literal["draft", "approved", "sent", "cancelled", "expired"]


class ScheduledNotificationDraft(BaseModel):
    title: str = Field(min_length=1, max_length=65)
    body: str = Field(min_length=1, max_length=178)
    game_id: Optional[str] = None
    audience: Literal["users", "devices", "all"] = "users"
    # Naive. With local_time (default) it is a wall-clock time each device reaches in its own
    # timezone; with local_time=False it is a UTC instant.
    send_at: datetime
    local_time: bool = True
    # Why this was drafted. Shown on the approval screen next to the copy.
    rationale: Optional[str] = Field(default=None, max_length=500)
    source: Literal["admin", "claude"] = "admin"

    @field_validator("send_at")
    @classmethod
    def drop_tzinfo(cls, v: datetime) -> datetime:
        # Stored naive; convert an aware value to UTC first so "17:00+01:00" is not read as 17:00.
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class ScheduledNotificationBatchCreate(BaseModel):
    drafts: list[ScheduledNotificationDraft] = Field(min_length=1, max_length=50)


class ScheduledNotificationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=65)
    body: Optional[str] = Field(default=None, min_length=1, max_length=178)
    send_at: Optional[datetime] = None
    status: Optional[Literal["draft", "approved", "cancelled"]] = None

    @field_validator("send_at")
    @classmethod
    def drop_tzinfo(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class ScheduledNotificationRead(BaseModel):
    id: str
    batch_id: Optional[str]
    title: str
    body: str
    data: Optional[dict]
    audience: str
    send_at: datetime
    local_time: bool
    status: str
    source: str
    rationale: Optional[str]
    sent_zones: list[str]
    approved_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "ScheduledNotificationRead":
        return cls(
            id=row.id, batch_id=row.batch_id, title=row.title, body=row.body,
            data=json.loads(row.data) if row.data else None,
            audience=row.audience, send_at=row.send_at, local_time=row.local_time,
            status=row.status, source=row.source, rationale=row.rationale,
            sent_zones=json.loads(row.sent_zones) if row.sent_zones else [],
            approved_at=row.approved_at, sent_at=row.sent_at, created_at=row.created_at,
        )


class BatchCreated(BaseModel):
    batch_id: str
    ids: list[str]


class BatchApproved(BaseModel):
    batch_id: str
    approved: int


class CampaignRead(BaseModel):
    key: str
    day: int
    title: str
    body: str


class NotificationTypeStats(BaseModel):
    type: str
    total: int
    sent: int
    failed: int
    no_token: int
    opened: int
    open_rate: Optional[float]  # opened / sent; None when nothing was sent


class ZoneCount(BaseModel):
    value: str
    count: int


class TimezoneHealth(BaseModel):
    total_tokens: int
    reported: int  # a valid zone is stored
    not_reported: int  # no zone and no error: builds that predate the field
    invalid: int  # the app sent a name that isn't an IANA zone
    utc: int  # reported as UTC / Etc/UTC
    utc_share: Optional[float]  # utc / reported; None when nothing has reported
    top_zones: list[ZoneCount]
    invalid_samples: list[ZoneCount]
    # Set when the numbers look like a broken client rather than real users.
    warning: Optional[str]
