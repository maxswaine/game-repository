import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import require_admin
from src.db.database import SessionLocal, get_db
from src.db.tables import Notification, PushToken, ScheduledNotification, User
from src.models.notification_models.admin_notification import AdminNotificationRequest
from src.models.notification_models.scheduled_notification import (
    BatchApproved, BatchCreated, CampaignRead, NotificationTypeStats, ScheduledNotificationBatchCreate,
    ScheduledNotificationRead, ScheduledNotificationUpdate, ScheduledStatus, TimezoneHealth, ZoneCount,
)
from src.services import notifications
from src.services.notification_automation import CAMPAIGNS, UTC_NAMES, timezone_warning

router = APIRouter()


def _broadcast_task(title: str, body: str, game_id: str | None, audience: str) -> None:
    db = SessionLocal()
    try:
        data = {"game_id": game_id} if game_id else None

        if audience in ("users", "all"):
            user_ids = [row.id for row in db.query(User.id).filter(User.is_active.is_(True)).all()]
            for user_id in user_ids:
                notifications.send(db, user_id, title, body, notification_type="custom", data=data)

        if audience in ("devices", "all"):
            notifications.send_to_anonymous_devices(
                db, title, body, notification_type="custom", data=data,
            )

        db.commit()
    finally:
        db.close()


@router.post("/notifications")
def send_admin_notification(
        db: Annotated[Session, Depends(get_db)],
        body: AdminNotificationRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(require_admin),
):
    data = {"game_id": body.game_id} if body.game_id else None

    if body.target == "user":
        target_user = db.query(User).filter(User.id == body.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        notifications.send(db, body.user_id, body.title, body.body, notification_type="custom", data=data)
        db.commit()
        return JSONResponse(status_code=200, content={"status": "sent"})

    background_tasks.add_task(_broadcast_task, body.title, body.body, body.game_id, body.audience)
    return JSONResponse(status_code=202, content={"status": "queued"})


# --- Approval queue ---------------------------------------------------------------------------
# Drafts are written by an admin or the weekly Claude routine; src/services/notification_automation.py
# sends only rows that reach "approved". A drafting run shares one batch_id so a week of copy can
# be reviewed as a calendar and approved in a single call.

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _approve(row: ScheduledNotification, admin: User) -> None:
    row.status = "approved"
    row.approved_by = admin.id
    row.approved_at = _now()


@router.post("/notifications/scheduled", status_code=201, response_model=BatchCreated)
def create_scheduled_drafts(
        db: Annotated[Session, Depends(get_db)],
        body: ScheduledNotificationBatchCreate,
        current_user: User = Depends(require_admin),
):
    batch_id = str(uuid.uuid4())
    rows = [
        ScheduledNotification(
            id=str(uuid.uuid4()), batch_id=batch_id, title=d.title, body=d.body,
            data=json.dumps({"game_id": d.game_id}) if d.game_id else None,
            audience=d.audience, send_at=d.send_at, local_time=d.local_time,
            status="draft", source=d.source, rationale=d.rationale,
        )
        for d in body.drafts
    ]
    db.add_all(rows)
    db.commit()
    return BatchCreated(batch_id=batch_id, ids=[r.id for r in rows])


@router.get("/notifications/scheduled", response_model=list[ScheduledNotificationRead])
def list_scheduled(
        db: Annotated[Session, Depends(get_db)],
        status: Optional[ScheduledStatus] = None,
        batch_id: Optional[str] = None,
        limit: int = Query(100, ge=1, le=200),
        current_user: User = Depends(require_admin),
):
    """The calendar. With no `status`, everything still to go out (draft + approved), soonest first."""
    q = db.query(ScheduledNotification)
    q = q.filter(ScheduledNotification.status == status) if status \
        else q.filter(ScheduledNotification.status.in_(("draft", "approved")))
    if batch_id:
        q = q.filter(ScheduledNotification.batch_id == batch_id)
    rows = q.order_by(ScheduledNotification.send_at, ScheduledNotification.created_at).limit(limit).all()
    return [ScheduledNotificationRead.from_row(r) for r in rows]


@router.patch("/notifications/scheduled/{notification_id}", response_model=ScheduledNotificationRead,
              responses={404: {"description": "Not found"}, 409: {"description": "Already sent, cancelled or expired"}})
def update_scheduled(
        db: Annotated[Session, Depends(get_db)],
        notification_id: str,
        body: ScheduledNotificationUpdate,
        current_user: User = Depends(require_admin),
):
    row = db.query(ScheduledNotification).filter(ScheduledNotification.id == notification_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled notification not found")
    if row.status not in ("draft", "approved"):
        raise HTTPException(status_code=409, detail=f"Already {row.status}")

    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    content_changed = any(changes.get(f) is not None and changes[f] != getattr(row, f)
                          for f in ("title", "body", "send_at"))
    for field in ("title", "body", "send_at"):
        if field in changes:
            setattr(row, field, changes[field])

    new_status = changes.get("status")
    if new_status == "approved":
        _approve(row, current_user)
    elif new_status == "cancelled":
        row.status = "cancelled"
    elif new_status == "draft" or (content_changed and row.status == "approved"):
        # Editing approved copy sends it back for review: what was approved is what goes out.
        row.status = "draft"
        row.approved_by = None
        row.approved_at = None

    db.commit()
    return ScheduledNotificationRead.from_row(row)


@router.post("/notifications/scheduled/batches/{batch_id}/approve", response_model=BatchApproved,
             responses={404: {"description": "No such batch"}})
def approve_batch(
        db: Annotated[Session, Depends(get_db)],
        batch_id: str,
        current_user: User = Depends(require_admin),
):
    """Approve every still-draft row in a batch. Cancel unwanted rows first with PATCH."""
    rows = db.query(ScheduledNotification).filter(ScheduledNotification.batch_id == batch_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Batch not found")
    drafts = [r for r in rows if r.status == "draft"]
    for row in drafts:
        _approve(row, current_user)
    db.commit()
    return BatchApproved(batch_id=batch_id, approved=len(drafts))


@router.get("/notifications/campaigns", response_model=list[CampaignRead])
def list_campaigns(current_user: User = Depends(require_admin)):
    """The fixed lifecycle campaigns that send automatically (copy lives in code, not the queue)."""
    return [CampaignRead(key=c.key, day=c.day, title=c.title, body=c.body) for c in CAMPAIGNS]


@router.get("/notifications/stats", response_model=list[NotificationTypeStats])
def notification_stats(
        db: Annotated[Session, Depends(get_db)],
        days: int = Query(30, ge=1, le=365),
        current_user: User = Depends(require_admin),
):
    """Delivery and open counts per notification type. A campaign at 0 sent shows up as a row here,
    which is how a silently broken automation gets noticed."""
    since = (_now() - timedelta(days=days)).replace(tzinfo=None)

    def count_where(cond):
        return func.sum(case((cond, 1), else_=0))

    rows = (
        db.query(
            Notification.type,
            func.count(Notification.id),
            count_where(Notification.status == "sent"),
            count_where(Notification.status == "failed"),
            count_where(Notification.status == "no_token"),
            count_where(Notification.opened_at.isnot(None)),
        )
        .filter(Notification.created_at >= since)
        .group_by(Notification.type)
        .order_by(func.count(Notification.id).desc())
        .all()
    )
    return [
        NotificationTypeStats(
            type=t, total=int(total), sent=int(sent), failed=int(failed), no_token=int(no_token),
            opened=int(opened), open_rate=round(int(opened) / int(sent), 3) if int(sent) else None,
        )
        for t, total, sent, failed, no_token, opened in rows
    ]


@router.get("/notifications/timezones", response_model=TimezoneHealth)
def timezone_health(
        db: Annotated[Session, Depends(get_db)],
        current_user: User = Depends(require_admin),
):
    """Is the app reporting real timezones? Mostly-UTC means a stripped Intl build is feeding us
    UTC (local-time sends silently collapse to 17:00 UTC); invalid names mean a client bug."""
    def count(*conds):
        return db.query(func.count(PushToken.token)).filter(*conds).scalar() or 0

    total = count()
    reported = count(PushToken.timezone.isnot(None))
    invalid = count(PushToken.timezone_error.isnot(None))
    utc = count(PushToken.timezone.in_(UTC_NAMES))
    utc_share = round(utc / reported, 3) if reported else None

    def top(column):
        rows = (db.query(column, func.count(PushToken.token)).filter(column.isnot(None))
                .group_by(column).order_by(func.count(PushToken.token).desc()).limit(10).all())
        return [ZoneCount(value=v, count=c) for v, c in rows]

    warning = timezone_warning(reported, utc, invalid)

    return TimezoneHealth(
        total_tokens=total, reported=reported, not_reported=total - reported - invalid, invalid=invalid,
        utc=utc, utc_share=utc_share, top_zones=top(PushToken.timezone),
        invalid_samples=top(PushToken.timezone_error), warning=warning,
    )
