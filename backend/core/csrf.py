import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status, Response

# Secret key for signing CSRF tokens (store in .env)
CSRF_SECRET = os.getenv("CSRF_SECRET", secrets.token_urlsafe(32))


def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_urlsafe(32)


def sign_csrf_token(token: str) -> str:
    """Create HMAC signature of CSRF token."""
    return hmac.new(
        CSRF_SECRET.encode(),
        token.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_csrf_token(token: str, signature: str) -> bool:
    """Verify CSRF token signature."""
    expected_signature = sign_csrf_token(token)
    return hmac.compare_digest(expected_signature, signature)


def set_csrf_cookie(response: Response, token: str):
    """Set CSRF token cookie."""
    signature = sign_csrf_token(token)

    # Store signature in cookie
    response.set_cookie(
        key="csrf_token",
        value=signature,
        httponly=False,  # Frontend needs to read this
        secure=os.getenv("ENVIRONMENT") == "production",  # True in production
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax",
        max_age=3600 * 24 * 7,  # 7 days
    )

    return token  # Return token for frontend to use in header


# Dependency for CSRF validation
async def validate_csrf_token(
        x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
        csrf_token: Optional[str] = Header(None, alias="csrf_token")
) -> None:
    if not x_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing in header"
        )

    if not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing in cookie"
        )

    if not verify_csrf_token(x_csrf_token, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )
