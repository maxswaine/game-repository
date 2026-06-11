import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from src.db.database import SessionLocal
from src.db.tables import User
from src.utils.config import DELETED_USER_ID


def seed_deleted_user() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.id == DELETED_USER_ID).first():
            print("deleted-user already exists, skipping")
            return
        placeholder = User(
            id=DELETED_USER_ID,
            firstname="Deleted",
            lastname="User",
            username="deleted-user",
            email="deleted@internal",
            hashed_password=None,
            is_active=False,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )
        db.add(placeholder)
        db.commit()
        print("deleted-user seeded successfully")
    finally:
        db.close()


if __name__ == "__main__":
    seed_deleted_user()
