from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from flask.cli import load_dotenv
from passlib.context import CryptContext

from backend.core.exceptions import UNAUTHORIZED_EXCEPTION
from backend.models.oauth_models.token import TokenData

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
TOKEN_EXPIRES_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
ALGORITHM = os.getenv("ALGORITHM")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --------------------
# Password hashing
# --------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --------------------
# JWT handling
# --------------------

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=int(TOKEN_EXPIRES_MINUTES)))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise UNAUTHORIZED_EXCEPTION
        return TokenData(username=username)
    except jwt.PyJWTError:
        raise UNAUTHORIZED_EXCEPTION
