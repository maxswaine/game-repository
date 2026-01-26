from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext

from backend.core.exceptions import FORBIDDEN_EXCEPTION
from backend.models.token import TokenData

SECRET_KEY = "DUMMY_KEY"  # move to env later
ALGORITHM = "HS256"
TOKEN_EXPIRES = timedelta(minutes=60)

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
    expire = datetime.now(timezone.utc) + (expires_delta or TOKEN_EXPIRES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise FORBIDDEN_EXCEPTION
        return TokenData(username=username)
    except jwt.PyJWTError:
        raise FORBIDDEN_EXCEPTION