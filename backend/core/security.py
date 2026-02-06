from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from backend.core.exceptions import UNAUTHORIZED_EXCEPTION
from backend.models.oauth_models.token import TokenData

SECRET_KEY = os.getenv("SECRET_KEY")
TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
ALGORITHM = os.getenv("ALGORITHM", "HS256")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    # Now TOKEN_EXPIRES_MINUTES is already an int, no need to convert
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRES_MINUTES)

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