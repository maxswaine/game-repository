import os
from pathlib import Path

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases
from src.core.limiter import limiter
from src.db.database import engine, Base

_version_file = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unknown"

app = FastAPI(version=APP_VERSION)
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


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}


@app.get("/version", tags=["meta"])
def get_version():
    return {"version": APP_VERSION}
