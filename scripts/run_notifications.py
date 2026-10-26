"""Hourly notification worker. Run by a Railway cron service:

    python -m scripts.run_notifications

Start command on the service, cron schedule `0 * * * *`. Same repo and DATABASE_URL as the API.
Exits non-zero on failure so Railway marks the run failed instead of quietly succeeding.
"""
import logging
import sys

from src.db.database import SessionLocal
from src.services.notification_automation import log_health, run_tick

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_notifications")


def main() -> int:
    db = SessionLocal()
    try:
        run_tick(db)
        db.commit()
        # After the commit, so a failing check can never roll back sends that already went out.
        log_health(db)
        return 0
    except Exception:
        db.rollback()
        logger.exception("Notification tick failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
