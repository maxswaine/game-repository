import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum
from backend.db.database import Base
from sqlalchemy.orm import relationship

from backend.models.enums import AgeRating, GameType, Role


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    username = Column(String, nullable=False)
    email = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    country_of_origin = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.user)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    games = relationship("Game", back_populates="contributor")

class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    age_rating = Column(Enum(AgeRating), nullable=False)
    game_type = Column(Enum(GameType), nullable=False)
    min_players = Column(Integer, nullable=False)
    max_players = Column(Integer, nullable=False)
    duration = Column(String, nullable=False)
    rules = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    is_public = Column(Boolean, nullable=False, default=True)
    upvotes = Column(Integer, nullable=False, default=0)
    downvotes = Column(Integer, nullable=False, default=0)
    contributor_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # relationships
    equipment_items = relationship("GameEquipment", cascade="all, delete-orphan")
    theme_items = relationship("GameTheme", cascade="all, delete-orphan")
    contributor = relationship("User", back_populates="games")

class GameEquipment(Base):
    __tablename__ = "game_equipment"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey("games.id"), nullable=False)
    equipment_name = Column(String, nullable=False)

class GameTheme(Base):
    __tablename__ = "game_themes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey("games.id"), nullable=False)
    theme_name = Column(String, nullable=False)