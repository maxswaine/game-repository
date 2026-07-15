from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from passlib.context import CryptContext

from src.core.exceptions import UNAUTHORIZED_EXCEPTION
from src.models.oauth_models.token import TokenData

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
ALGORITHM = os.getenv("ALGORITHM", "HS256")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password_length(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long")
    return password


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
        return TokenData(username=username, exp=payload.get("exp"), ver=payload.get("ver"))
    except jwt.PyJWTError:
        raise UNAUTHORIZED_EXCEPTION


PASSWORD_RESET_EXPIRES_MINUTES = 15


def create_password_reset_token(email: str, token_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRES_MINUTES)
    return jwt.encode(
        {"sub": email, "type": "password_reset", "exp": expire, "ver": token_version},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_password_reset_token(token: str) -> tuple[str, int]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            raise ValueError("Invalid token type")
        email: str | None = payload.get("sub")
        if not email:
            raise ValueError("Missing subject")
        ver = payload.get("ver")
        if ver is None:
            raise ValueError("Missing version")
        return email, int(ver)
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc