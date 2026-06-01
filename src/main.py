import os
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements
from src.db.database import engine, Base

_version_file = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unknown"

app = FastAPI(version=APP_VERSION)
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


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}


@app.get("/version", tags=["meta"])
def get_version():
    return {"version": APP_VERSION}
