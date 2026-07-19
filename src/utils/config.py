import os

from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUPLICATE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.85")
)
DELETED_USER_ID: str = "00000000-0000-0000-0000-000000000001"
# Host that serves short links at root (e.g. qr.example/instagram -> /qr/instagram)
QR_HOST: str = os.getenv("QR_HOST", "qr.whatsthatgame.co.uk")
