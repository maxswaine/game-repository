from fastapi import FastAPI

from backend.api import users, games, auth
from backend.db.database import engine, Base

app = FastAPI()
Base.metadata.create_all(bind=engine)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(games.protected_router, prefix="/games", tags=["games"])
app.include_router(games.public_router, prefix="/games", tags=["games"])
app.include_router(auth.router, prefix="", tags=["auth"])


@app.get("/")
def read_root():
    return {"message": "Welcome to Games Repository API"}
