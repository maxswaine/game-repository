import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from backend.db.database import Base
from backend.models.enums.age_rating_enum import AgeRatingEnum
from backend.models.enums.equipment_enum import GameEquipmentEnum
from backend.models.enums.game_theme_enum import GameThemeEnum
from backend.models.enums.game_type_enum import GameTypeEnum
from backend.models.enums.role_enum import Role

GAMES_ID_FK: str = "games.id"

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    username = Column(String, nullable=False)
    email = Column(String, nullable=False)
    hashed_password = Column(String, nullable=True)
    date_of_birth = Column(String, nullable=True)
    country_of_origin = Column(String(2), nullable=True)
    role = Column(Enum(Role), nullable=False, default=Role.user)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    oauth_provider = Column(String, nullable=True)
    oauth_id = Column(String, nullable=True, unique=True)
    avatar_url = Column(String, nullable=True)

    games = relationship("Game", back_populates="contributor")
    favourites = relationship("UserFavourites", back_populates="user")


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
    age_rating = Column(Enum(AgeRatingEnum), nullable=False)

    game_type = Column(Enum(GameTypeEnum), nullable=False)

    min_players = Column(Integer, nullable=False)
    max_players = Column(Integer, nullable=False)
    duration = Column(String, nullable=False)
    rules = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    is_public = Column(Boolean, nullable=False, default=True)
    is_whats_that_game_verified = Column(Boolean, nullable=False, default=False)

    upvotes = Column(Integer, nullable=False, default=0)
    downvotes = Column(Integer, nullable=False, default=0)

    contributor_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # relationships
    equipment_items = relationship("GameEquipment", cascade="all, delete-orphan")
    theme_items = relationship("GameTheme", cascade="all, delete-orphan")
    contributor = relationship("User", back_populates="games")
    favourited_by = relationship("UserFavourites", back_populates="game", lazy="noload")


class GameEquipment(Base):
    __tablename__ = "game_equipment"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK), nullable=False)
    equipment_name = Column(Enum(GameEquipmentEnum), nullable=False)


class GameTheme(Base):
    __tablename__ = "game_themes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey(GAMES_ID_FK), nullable=False)
    theme_name = Column(Enum(GameThemeEnum), nullable=False)