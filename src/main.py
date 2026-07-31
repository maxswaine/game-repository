import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links, photos, push_tokens, admin_notifications, avatar, game_review
from src.core.limiter import limiter
from src.core.scheduler import scheduler
from src.db.database import engine, Base, SessionLocal
from src.services.purge import run_purge
from src.services.receipts import check_pending_deliveries
from src.utils.config import QR_HOST

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_version_file = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unknown"

def _run_purge_job() -> None:
    db = SessionLocal()
    try:
        run_purge(db)
    finally:
        db.close()


def _run_check_receipts_job() -> None:
    db = SessionLocal()
    try:
        check_pending_deliveries(db)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if engine.dialect.name != "sqlite":
        if not scheduler.get_job("daily_purge"):
            scheduler.add_job(_run_purge_job, "cron", hour=0, minute=0, id="daily_purge")
        if not scheduler.get_job("check_push_receipts"):
            scheduler.add_job(_run_check_receipts_job, "interval", minutes=15, id="check_push_receipts")
        if not scheduler.running:
            scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan, version=APP_VERSION)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def log_validation_errors(request: Request, exc: RequestValidationError):
    body = exc.body
    logger.warning(
        "422 validation error on %s %s: errors=%s body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        body,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())},
    )

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SessionMiddleware, secret_key=os.environ["SECRET_KEY"])
Base.metadata.create_all(bind=engine)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
print(f"CORS Origins configured: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(games.protected_router, prefix="/games", tags=["games"])
app.include_router(games.public_router, prefix="/games", tags=["games"])
app.include_router(auth.router, prefix="", tags=["auth", "oauth"])
app.include_router(favourites.router, prefix="/favourites", tags=["favourites"])
app.include_router(metadata.router, prefix="/metadata", tags=["metadata"])
app.include_router(optimisation.router, prefix="/optimise", tags=["optimisation"])
app.include_router(search.router, prefix="/games/search", tags=["search"])
app.include_router(achievements.router, prefix="/achievements", tags=["achievements"])
app.include_router(aliases.public_router, prefix="/games", tags=["aliases"])
app.include_router(aliases.admin_router, prefix="/admin", tags=["admin"])
app.include_router(comments.router, prefix="/games", tags=["comments"])
app.include_router(photos.router, prefix="/games", tags=["photos"])
app.include_router(avatar.router, prefix="/users", tags=["avatar"])
app.include_router(push_tokens.router, prefix="/push-tokens", tags=["push-tokens"])
app.include_router(admin_notifications.router, prefix="/admin", tags=["admin"])
app.include_router(game_review.admin_router, prefix="/admin", tags=["admin"])
app.include_router(feedback.router, prefix="", tags=["feedback"])
app.include_router(feedback.admin_router, prefix="/admin", tags=["admin"])
app.include_router(short_links.public_router, prefix="", tags=["short_links"])
app.include_router(short_links.admin_router, prefix="/admin", tags=["short_links"])
app.add_middleware(short_links.QRHostRewrite, qr_host=QR_HOST)


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}


@app.get("/version", tags=["meta"])
def get_version():
    return {"version": APP_VERSION}
