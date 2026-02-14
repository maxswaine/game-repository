import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from backend.api import users, games, auth, favourites, metadata
from backend.db.database import engine, Base

app = FastAPI()
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


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}
