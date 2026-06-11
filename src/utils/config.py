import os

from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUPLICATE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.88")
)
