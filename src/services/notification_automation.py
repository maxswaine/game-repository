"""Automated push campaigns: lifecycle nudges plus an approval queue.

`run_tick()` is the single entry point, called hourly by scripts/run_notifications.py. All
delivery goes through `notifications.send*`, so Expo handling, dead-token pruning and the
Notification / PushDeliveryTicket trace are the existing, tested path. This module only decides
*who* gets a push and *when*.

Two sources of pushes, one set of guardrails:
  * CAMPAIGNS    - lifecycle nudges ("two days in, no game added yet"). Copy lives in code, so it is
                   reviewed in a PR and needs no per-send approval.
  * ScheduledNotification rows - copy written by an admin or the weekly Claude routine. Nothing
                   sends until a human moves it draft -> approved (whole batches at once).

Guardrails, applied to both: the kill switch, a weekly cap per user, one automated push per
user per tick, and judging "when" in each device's own timezone.

Delivery is at-most-once on purpose: a row or zone is marked done *before* it is sent, so a crash
loses a push rather than sending it twice.
"""
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, false, func, or_, text, true
from sqlalchemy.orm import Query, Session

from src.db.tables import Game, Notification, PushToken, ScheduledNotification, User, UserFavourites
from src.services import notifications
from src.utils import config

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")
# Key for devices whose app build predates the timezone field. Treated as UTC.
NO_ZONE = "~unset"
# A user who signed up N days ago is still picked up for up to this many extra days, so a missed
# tick (deploy, outage) delays a nudge instead of silently dropping the cohort.
CATCHUP_DAYS = 3
DORMANT_DAYS = 10
# Earliest zone is UTC+14, latest UTC-12: a local-time row spans this many hours.
_EARLIEST_ZONE_HOURS, _LATEST_ZONE_HOURS = 14, 12
# How late a zone may be reached after its local send time. Hourly ticks hit each zone within an
# hour, so this only absorbs a missed tick or two; far more would push people at 4am.
_LOCAL_GRACE = timedelta(hours=3)
# Arbitrary constant: pg_try_advisory_xact_lock key that serialises ticks across processes.
_LOCK_KEY = 7_203_141


# --------------------------------------------------------------------------------------------
# Timezones
# --------------------------------------------------------------------------------------------

def parse_zone(name: Optional[str]) -> Optional[ZoneInfo]:
    """The zone for an IANA name, or None if it isn't one. Never raises."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        logger.warning("Unrecognised timezone name %r", name)
        return None


def _zone_or_utc(key: Optional[str]) -> ZoneInfo:
    return UTC if key in (None, NO_ZONE) else (parse_zone(key) or UTC)


def _naive(dt: datetime) -> datetime:
    """Naive UTC, which is how every DateTime column in this schema is stored."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _local_now(now: datetime, key: Optional[str]) -> datetime:
    return now.astimezone(_zone_or_utc(key)).replace(tzinfo=None)


def _zone_keys(db: Session) -> list[str]:
    """Every distinct timezone a registered device reports, with NO_ZONE for unset."""
    return [z if z is not None else NO_ZONE for (z,) in db.query(PushToken.timezone).distinct().all()]


def _zone_cond(keys: list[str]):
    """SQL condition matching tokens whose timezone is one of `keys` (NO_ZONE = unset)."""
    named = [k for k in keys if k != NO_ZONE]
    clauses = []
    if named:
        clauses.append(PushToken.timezone.in_(named))
    if NO_ZONE in keys:
        clauses.append(PushToken.timezone.is_(None))
    return or_(*clauses) if clauses else false()


# --------------------------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------------------------

def _at_cap(db: Session, user_id: str, nn: datetime) -> bool:
    """True once a user has had the weekly maximum of automated (campaign/lifecycle) pushes."""
    sent = db.query(func.count(Notification.id)).filter(
        Notification.user_id == user_id,
        Notification.created_at >= nn - timedelta(days=7),
        or_(
            Notification.type.startswith("lifecycle_", autoescape=True),
            Notification.type.startswith("campaign_", autoescape=True),
        ),
    ).scalar()
    return sent >= config.NOTIFICATION_WEEKLY_CAP


def _push_user(db, nn, user_id, tokens, key, title, body, data, sent_this_tick) -> bool:
    """Send one automated push to one user, unless a guardrail says no."""
    if user_id in sent_this_tick or _at_cap(db, user_id, nn):
        return False
    notifications.send_to_tokens(db, tokens, user_id, title, body, notification_type=key, data=data)
    # autoflush is off in this app, and the cap/dedupe queries must see this row.
    db.flush()
    sent_this_tick.add(user_id)
    return True


# --------------------------------------------------------------------------------------------
# Lifecycle campaigns
# --------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Campaign:
    key: str  # becomes Notification.type, which is also the dedupe key: one per user, ever
    day: int  # days after users.created_at
    title: str
    body: str
    # Narrows a (User join PushToken) query to who should actually get it.
    narrow: Callable[[Query, datetime], Query]


def _no_submissions(q: Query, nn: datetime) -> Query:
    return q.filter(~exists().where(Game.contributor_id == User.id))


def _no_likes(q: Query, nn: datetime) -> Query:
    return q.filter(~exists().where(UserFavourites.user_id == User.id))


def _has_approved_game(q: Query, nn: datetime) -> Query:
    return q.filter(exists().where(Game.contributor_id == User.id, Game.status == "approved"))


def _dormant(q: Query, nn: datetime) -> Query:
    # PushToken.updated_at is re-stamped on every app launch (src/api/push_tokens.py), so an old
    # one means the app hasn't been opened. It is the only last-seen signal the schema has.
    return q.filter(PushToken.updated_at < nn - timedelta(days=DORMANT_DAYS))


CAMPAIGNS: list[Campaign] = [
    Campaign("lifecycle_day_2_no_submit", 2, "Know a game we don't?",
             "Add one game and you'll unlock your first achievement.", _no_submissions),
    Campaign("lifecycle_day_3_no_like", 3, "Found your favourite yet?",
             "Tap the heart on any game to save it to your list.", _no_likes),
    Campaign("lifecycle_day_7_submitted", 7, "Your game is out there",
             "Come and see how many likes it has picked up.", _has_approved_game),
    Campaign("lifecycle_day_14_dormant", 14, "New games this week",
             "Have a look at what's been added.", _dormant),
]


def _cohort(db: Session, c: Campaign, nn: datetime, zone_cond) -> dict[str, list[PushToken]]:
    """user_id -> that user's tokens in the matching zones, for users due campaign `c`."""
    q = (
        db.query(PushToken)
        .join(User, User.id == PushToken.user_id)
        .filter(
            User.is_active.is_(True),
            User.deletion_requested_at.is_(None),
            User.created_at <= nn - timedelta(days=c.day),
            User.created_at > nn - timedelta(days=c.day + CATCHUP_DAYS),
            zone_cond,
            ~exists().where(Notification.user_id == User.id, Notification.type == c.key),
        )
    )
    by_user: dict[str, list[PushToken]] = defaultdict(list)
    for token in c.narrow(q, nn).all():
        by_user[token.user_id].append(token)
    return by_user


def run_lifecycle(db: Session, now: datetime, sent_this_tick: set) -> int:
    nn = _naive(now)
    # Only devices where it is currently NOTIFICATION_SEND_HOUR o'clock. Hourly ticks mean each
    # zone passes through that hour exactly once a day.
    due_zones = [k for k in _zone_keys(db) if _local_now(now, k).hour == config.NOTIFICATION_SEND_HOUR]
    if not due_zones:
        return 0
    zone_cond = _zone_cond(due_zones)

    pushed = 0
    for c in CAMPAIGNS:
        # One campaign failing must not cancel the others; the trace is the log line.
        try:
            for user_id, tokens in _cohort(db, c, nn, zone_cond).items():
                if _push_user(db, nn, user_id, tokens, c.key, c.title, c.body,
                              {"campaign": c.key}, sent_this_tick):
                    pushed += 1
        except Exception:
            logger.exception("Lifecycle campaign %s failed", c.key)
    return pushed


# --------------------------------------------------------------------------------------------
# Approval queue
# --------------------------------------------------------------------------------------------

def _send_row(db: Session, row: ScheduledNotification, nn: datetime, zone_keys: Optional[list[str]],
              sent_this_tick: set) -> int:
    """Deliver one queue row to its audience. zone_keys=None means every device."""
    key = f"campaign_{row.id}"
    data = json.loads(row.data) if row.data else None
    cond = true() if zone_keys is None else _zone_cond(zone_keys)
    pushed = 0

    if row.audience in ("users", "all"):
        by_user: dict[str, list[PushToken]] = defaultdict(list)
        tokens = (
            db.query(PushToken).join(User, User.id == PushToken.user_id)
            .filter(User.is_active.is_(True), cond).all()
        )
        for token in tokens:
            by_user[token.user_id].append(token)
        for user_id, user_tokens in by_user.items():
            if _push_user(db, nn, user_id, user_tokens, key, row.title, row.body, data, sent_this_tick):
                pushed += 1

    if row.audience in ("devices", "all"):
        anon = db.query(PushToken).filter(PushToken.user_id.is_(None), cond).all()
        if anon:
            notifications.send_to_tokens(
                db, anon, None, row.title, row.body, notification_type=key, data=data,
            )
            pushed += len(anon)
    return pushed


def _process_row(db: Session, row: ScheduledNotification, now: datetime, sent_this_tick: set) -> int:
    nn = _naive(now)
    stale = timedelta(hours=config.NOTIFICATION_STALE_HOURS)
    sent_zones = set(json.loads(row.sent_zones)) if row.sent_zones else set()

    if row.local_time:
        # Past the point where even the last-arriving zone's window has closed.
        finished = nn >= row.send_at + timedelta(hours=_LATEST_ZONE_HOURS) + _LOCAL_GRACE
        not_started = nn < row.send_at - timedelta(hours=_EARLIEST_ZONE_HOURS)
    else:
        finished = nn >= row.send_at + stale
        not_started = nn < row.send_at

    if finished:
        if row.status == "approved" and sent_zones:
            row.status = "sent"
        else:
            logger.warning("Scheduled notification %s expired unsent (was %s)", row.id, row.status)
            row.status = "expired"
        return 0
    if row.status != "approved" or not_started:
        return 0

    if not row.local_time:
        row.status = "sent"  # marked before sending: at-most-once
        row.sent_at = now
        return _send_row(db, row, nn, None, sent_this_tick)

    due = [
        k for k in _zone_keys(db)
        if k not in sent_zones and row.send_at <= _local_now(now, k) < row.send_at + _LOCAL_GRACE
    ]
    if not due:
        return 0
    row.sent_zones = json.dumps(sorted(sent_zones | set(due)))
    row.sent_at = row.sent_at or now
    return _send_row(db, row, nn, due, sent_this_tick)


def process_queue(db: Session, now: datetime, sent_this_tick: set) -> int:
    rows = (
        db.query(ScheduledNotification)
        .filter(ScheduledNotification.status.in_(("draft", "approved")))
        .order_by(ScheduledNotification.send_at)
        .all()
    )
    pushed = 0
    for row in rows:
        try:
            pushed += _process_row(db, row, now, sent_this_tick)
        except Exception:
            logger.exception("Scheduled notification %s failed", row.id)
    return pushed


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------

def run_tick(db: Session, now: Optional[datetime] = None) -> dict:
    """One pass of both sources. The caller commits."""
    if not config.NOTIFICATION_AUTOMATION_ENABLED:
        logger.info("Notification automation disabled (NOTIFICATION_AUTOMATION_ENABLED) - tick skipped")
        return {"enabled": False}

    now = now or datetime.now(timezone.utc)

    if db.get_bind().dialect.name == "postgresql":
        # Held until the caller commits, so two overlapping ticks (a slow run, a second replica)
        # cannot both read "not sent yet" and send twice.
        if not db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _LOCK_KEY}).scalar():
            logger.warning("Another notification tick holds the lock - skipping this one")
            return {"enabled": True, "locked": True}

    sent_this_tick: set = set()
    queued = process_queue(db, now, sent_this_tick)
    lifecycle = run_lifecycle(db, now, sent_this_tick)
    logger.info("Notification tick done: queue_pushes=%s lifecycle_pushes=%s", queued, lifecycle)
    return {"enabled": True, "queued": queued, "lifecycle": lifecycle}


# --------------------------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------------------------

UTC_NAMES = ("UTC", "Etc/UTC")
MIN_REPORTED_FOR_UTC_WARNING = 20


def timezone_warning(reported: int, utc: int, invalid: int) -> Optional[str]:
    """Why the timezone numbers look like a broken client, or None if they look fine."""
    # ponytail: fixed 50% / 20-device threshold, tune if real traffic is mostly UTC (UK-heavy)
    if reported >= MIN_REPORTED_FOR_UTC_WARNING and utc / reported >= 0.5:
        return f"{utc / reported:.0%} of reporting devices say UTC: check Intl on a release build"
    if invalid:
        return f"{invalid} device(s) sent a timezone name that is not an IANA zone"
    return None


def health_warnings(db: Session, now: Optional[datetime] = None) -> list[str]:
    """Things that mean the automation is quietly not doing its job. Read-only."""
    now = _naive(now or datetime.now(timezone.utc))
    problems = []

    reported = db.query(func.count(PushToken.token)).filter(PushToken.timezone.isnot(None)).scalar() or 0
    utc = db.query(func.count(PushToken.token)).filter(PushToken.timezone.in_(UTC_NAMES)).scalar() or 0
    invalid = db.query(func.count(PushToken.token)).filter(PushToken.timezone_error.isnot(None)).scalar() or 0
    if message := timezone_warning(reported, utc, invalid):
        problems.append(message)

    # process_queue sends or expires an approved row within hours; one this old was missed entirely.
    stuck = (db.query(func.count(ScheduledNotification.id))
             .filter(ScheduledNotification.status == "approved",
                     ScheduledNotification.send_at < now - timedelta(days=2)).scalar() or 0)
    if stuck:
        problems.append(f"{stuck} approved scheduled notification(s) are over 2 days past send_at and never sent")
    return problems


def log_health(db: Session) -> list[str]:
    """Log each problem at WARNING so it shows in Railway logs. Never raises: a broken check
    must not turn a tick that already sent its pushes into a failed run."""
    try:
        problems = health_warnings(db)
    except Exception:
        logger.exception("Notification health check failed")
        return []
    for problem in problems:
        logger.warning("Notification health: %s", problem)
    return problems
