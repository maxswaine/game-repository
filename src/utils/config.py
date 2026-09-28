import os

from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUPLICATE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.85")
)
# Cosine scores at or above DUPLICATE_SIMILARITY_THRESHOLD auto-flag as a duplicate. Scores between
# this floor and that threshold are borderline — different write-ups of the same game often land
# here — so they get a second look from an LLM judge instead of being silently approved.
DUPLICATE_CANDIDATE_THRESHOLD: float = float(
    os.getenv("DUPLICATE_CANDIDATE_THRESHOLD", "0.55")
)
# Caps how many borderline candidates get sent to the LLM judge per submission (cost/latency control).
DUPLICATE_LLM_CANDIDATE_LIMIT: int = int(
    os.getenv("DUPLICATE_LLM_CANDIDATE_LIMIT", "5")
)
DUPLICATE_LLM_JUDGE_MODEL: str = os.getenv("DUPLICATE_LLM_JUDGE_MODEL", "gpt-4.1-nano")
DELETED_USER_ID: str = "00000000-0000-0000-0000-000000000001"

# Lowest app semver still allowed to call the API without a client-side "please update" prompt.
# Empty string means no minimum is enforced (default — don't block anyone until this is set deliberately).
MIN_SUPPORTED_APP_VERSION: str = os.getenv("MIN_SUPPORTED_APP_VERSION", "")

# TEMPORARY: gates the game review/approval flow (pending-by-default submissions).
# Off by default so existing users see no behavior change until the FE ships "pending review"
# messaging. Flip to "true" once ready, then delete this flag entirely once the app is live
# on the App Store and every client build has the messaging.
GAME_REVIEW_GATE_ENABLED: bool = os.getenv("GAME_REVIEW_GATE_ENABLED", "false").lower() == "true"
# Host that serves short links at root (e.g. qr.example/instagram -> /qr/instagram)
QR_HOST: str = os.getenv("QR_HOST", "qr.whatsthatgame.co.uk")

# Resend audience for the public mailing list
RESEND_AUDIENCE_ID: str = os.getenv("RESEND_AUDIENCE_ID", "")

# Cloudflare R2 photo storage
R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET: str = os.getenv("R2_BUCKET", "")
R2_QUARANTINE_BUCKET: str = os.getenv("R2_QUARANTINE_BUCKET", "")
R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
