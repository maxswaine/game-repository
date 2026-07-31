import os

from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUPLICATE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.85")
)
DELETED_USER_ID: str = "00000000-0000-0000-0000-000000000001"

# TEMPORARY: gates the game review/approval flow (pending-by-default submissions).
# Off by default so existing users see no behavior change until the FE ships "pending review"
# messaging. Flip to "true" once ready, then delete this flag entirely once the app is live
# on the App Store and every client build has the messaging.
GAME_REVIEW_GATE_ENABLED: bool = os.getenv("GAME_REVIEW_GATE_ENABLED", "false").lower() == "true"
# Host that serves short links at root (e.g. qr.example/instagram -> /qr/instagram)
QR_HOST: str = os.getenv("QR_HOST", "qr.whatsthatgame.co.uk")

# Cloudflare R2 photo storage
R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET: str = os.getenv("R2_BUCKET", "")
R2_QUARANTINE_BUCKET: str = os.getenv("R2_QUARANTINE_BUCKET", "")
R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
