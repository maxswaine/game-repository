import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum, Text, select, func
from sqlalchemy.orm import relationship, column_property, deferred

from src.db.database import Base
from src.models.enums.role_enum import Role

GAMES_ID_FK: str = "games.id"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=True)
    date_of_birth = Column(String, nullable=True)
    country_of_origin = Column(String(2), nullable=True)
    role = Column(Enum(Role), nullable=False, default=Role.user)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    deletion_requested_at = Column(DateTime, nullable=True)
    oauth_provider = Column(String, nullable=True)
    oauth_id = Column(String, nullable=True, unique=True)
    avatar_url = Column(String, nullable=True)
    token_version = Column(Integer, nullable=True, default=0)
    user_segment = Column(String, nullable=True)
    user_segment_other = Column(String, nullable=True)
    # Asked at deletion time: keep this user's games, or delete them with the
    # account. False is both the default and what an unasked caller gets, which
    # is the pre-existing behaviour (private games go with the account).
    keep_games_on_delete = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    games = relationship("Game", back_populates="contributor", foreign_keys="Game.contributor_id")
    favourites = relationship("UserFavourites", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")


class UserFavourites(Base):
    __tablename__ = "user_favourites"
    game_id = Column(String, ForeignKey(GAMES_ID_FK), nullable=False, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Add relationships
    user = relationship("User", back_populates="favourites")
    game = relationship("Game", back_populates="favourited_by")


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    game_type = Column(String, nullable=False)
    min_players = Column(Integer, nullable=False)
    max_players = Column(Integer, nullable=False)
    duration = Column(String, nullable=False)
    objective = Column(String, nullable=False)
    setup = Column(String, nullable=False)
    rules = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    is_public = Column(Boolean, nullable=False, default=True)
    is_whats_that_game_verified = Column(Boolean, nullable=False, default=False)

    upvotes = Column(Integer, nullable=False, default=0)
    difficulty = Column(String, nullable=True)
    embedding = Column(String, nullable=True)  # JSON array of floats from text-embedding-3-small
    has_adult_content = Column(Boolean, nullable=False, default=False)

    # True when the contributor re-posted with ?force=true after the duplicate check returned 409.
    # Without this the bypass left no trace, so a forced duplicate was indistinguishable from one
    # the check never flagged (the check is best-effort and swallows its own failures).
    force_submitted = Column(Boolean, nullable=False, default=False)

    status = Column(String, nullable=False, default="pending")  # pending | approved | rejected
    rejection_reason_code = Column(String, nullable=True)  # GameRejectionReasonEnum value
    rejection_reason = Column(String, nullable=True)  # optional free-text detail from the admin
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    contributor_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # relationships
    equipment_items = relationship("GameEquipment", cascade="all, delete-orphan")
    setting_items = relationship("GameSetting", cascade="all, delete-orphan")
    contributor = relationship("User", back_populates="games", foreign_keys=[contributor_id])
    favourited_by = relationship(
        "UserFavourites", back_populates="game", lazy="noload", cascade="all, delete-orphan"
    )
    alias_objects = relationship("GameAlias", cascade="all, delete-orphan")
    photos = relationship(
        "GamePhoto",
        cascade="all, delete-orphan",
        order_by="GamePhoto.position",
    )
    videos = relationship(
        "GameVideo",
        cascade="all, delete-orphan",
        order_by="GameVideo.created_at",
    )


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id = Column(String, ForeignKey("users.id"), nullable=False, primary_key=True)
    achievement_type = Column(String, nullable=False, primary_key=True)
    achieved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="achievements")


class GameReport(Base):
    __tablename__ = "game_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK, ondelete="CASCADE"), nullable=False)
    reporter_id = Column(String, ForeignKey("users.id"), nullable=False)
    reason = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    game = relationship("Game")
    reporter = relationship("User", foreign_keys=[reporter_id])

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("game_id", "reporter_id", name="uq_game_report_per_user"),
    )


class GameEquipment(Base):
    __tablename__ = "game_equipment"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK), nullable=False)
    equipment_name = Column(String, nullable=False)


class GameSetting(Base):
    __tablename__ = "game_settings"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK), nullable=False)
    setting_name = Column(String, nullable=False)


class GamePhoto(Base):
    __tablename__ = "game_photos"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK, ondelete="CASCADE"), nullable=False, index=True)
    object_key = Column(String, nullable=False)
    public_url = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class GameVideo(Base):
    __tablename__ = "game_videos"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK, ondelete="CASCADE"), nullable=False, index=True)
    object_key = Column(String, nullable=False)
    public_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class GameAlias(Base):
    __tablename__ = "game_aliases"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK, ondelete="CASCADE"), nullable=False)
    alias = Column(String, nullable=False)
    suggested_by = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime, nullable=True)


class GameComment(Base):
    __tablename__ = "game_comments"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK, ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(String, nullable=False)
    comment_type = Column(String, nullable=False, default="general")
    likes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys="[GameComment.user_id]")
    like_records = relationship("CommentLike", cascade="all, delete-orphan")


class CommentLike(Base):
    __tablename__ = "comment_likes"
    comment_id = Column(String, ForeignKey("game_comments.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class PushToken(Base):
    __tablename__ = "push_tokens"
    token = Column(String, primary_key=True)
    # Nullable: a device that granted push permission before ever signing in owns a row with
    # no user. Signing in claims that row (see src/api/push_tokens.py); signing out leaves the
    # token deleted, not re-anonymised, because the app uses the same call for "log out" and
    # "turn notifications off" and the latter must actually stop delivery.
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    # Client-generated, stable per install. Lets a device keep one row across Expo token
    # rotation and across sign-in, so audience="all" never sends to the same device twice.
    device_id = Column(String, nullable=True, index=True)
    # IANA zone name (e.g. "Europe/London") the app reads off the phone at registration. Per
    # device rather than per user so signed-out devices and travellers are covered. Null means
    # an app build that predates the field; automation treats those devices as UTC.
    timezone = Column(String, nullable=True)
    # The last name the app sent that wasn't a real IANA zone. Cleared once a valid one arrives.
    # Lets /admin/notifications/timezones count bad reports instead of only logging them.
    timezone_error = Column(String, nullable=True)
    platform = Column(String, nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Nullable for broadcasts to anonymous devices — there is no user to attribute them to.
    # The per-token trace for those lives in push_delivery_tickets.
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    data = Column(String, nullable=True)
    achievement_type = Column(String, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    opened_at = Column(DateTime, nullable=True)


class ScheduledNotification(Base):
    """A campaign push waiting in the approval queue (see src/services/notification_automation.py).

    Drafts are written by an admin or the weekly Claude routine; nothing sends until a human
    moves it to "approved". Rows from one drafting run share a batch_id so a whole week can be
    reviewed and approved in one call.
    """
    __tablename__ = "scheduled_notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    data = Column(String, nullable=True)
    audience = Column(String, nullable=False, default="users")  # users | devices | all
    # Naive datetime. local_time=False: a UTC instant. local_time=True: a wall-clock time that
    # each device reaches in its own timezone, so one row fans out over ~26 hours.
    send_at = Column(DateTime, nullable=False, index=True)
    local_time = Column(Boolean, nullable=False, default=True)
    # draft | approved | sent | cancelled | expired
    status = Column(String, nullable=False, default="draft", index=True)
    source = Column(String, nullable=False, default="admin")  # admin | claude
    rationale = Column(String, nullable=True)  # why it was drafted; shown on the approval screen
    # JSON list of timezone names already delivered to, so a local_time row never re-sends.
    sent_zones = Column(Text, nullable=True)
    approved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class PushDeliveryTicket(Base):
    __tablename__ = "push_delivery_tickets"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id = Column(String, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, nullable=False)
    ticket_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    checked_at = Column(DateTime, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])


class ShortLink(Base):
    __tablename__ = "short_links"
    code = Column(String, primary_key=True)
    target_url = Column(String, nullable=False)
    label = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    scan_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# Profile contribution stats, derived rather than stored: they read the same
# Game.upvotes counter the game cards do, so they can never disagree with it.
# deferred => not in the default User SELECT, so the auth dependency that runs
# on every authenticated request does not pay for them; they load on first
# access, which in practice is only UserPrivateRead serialisation.
# ponytail: correlated subqueries over games.contributor_id, an unindexed FK.
# Index it when games outgrows a few thousand rows (needs manual SQL, no Alembic).
User.games_uploaded = deferred(
    column_property(
        select(func.count(Game.id))
        .where(Game.contributor_id == User.id)
        .scalar_subquery()
    )
)
User.likes_received = deferred(
    column_property(
        select(func.coalesce(func.sum(Game.upvotes), 0))
        .where(Game.contributor_id == User.id)
        .scalar_subquery()
    )
)
