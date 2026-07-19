import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links
from src.core.limiter import limiter
from src.core.scheduler import scheduler
from src.db.database import engine, Base, SessionLocal
from src.services.purge import run_purge

_version_file = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unknown"

def _run_purge_job() -> None:
    db = SessionLocal()
    try:
        run_purge(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if engine.dialect.name != "sqlite":
        if not scheduler.get_job("daily_purge"):
            scheduler.add_job(_run_purge_job, "cron", hour=0, minute=0, id="daily_purge")
        if not scheduler.running:
            scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan, version=APP_VERSION)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "changeme"))
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
app.include_router(feedback.router, prefix="", tags=["feedback"])
app.include_router(short_links.public_router, prefix="", tags=["short_links"])
app.include_router(short_links.admin_router, prefix="/admin", tags=["short_links"])


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}


@app.get("/version", tags=["meta"])
def get_version():
    return {"version": APP_VERSION}
