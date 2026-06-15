# src/api/auth.py
import json
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Annotated

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from fastapi import APIRouter, Depends, HTTPException, Cookie, Header, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, JSONResponse

from src.core.exceptions import UNAUTHORIZED_EXCEPTION, INACTIVE_USER_EXCEPTION
from src.core.limiter import limiter
from src.core.security import create_access_token, verify_access_token
from src.core.security import verify_password, TOKEN_EXPIRES_MINUTES
from src.db.database import get_db
from src.db.tables import User

IS_PRODUCTION = os.getenv("ENV") == "production"

router = APIRouter(prefix="/auth")

# Single-use exchange codes: code -> (jwt_token, expires_at)
_exchange_codes: dict[str, tuple[str, datetime]] = {}

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_apple_jwks_cache: list[dict] | None = None
_apple_jwks_cache_expires: datetime | None = None


async def _get_apple_jwks() -> list[dict]:
    global _apple_jwks_cache, _apple_jwks_cache_expires
    now = datetime.now(timezone.utc)
    if _apple_jwks_cache is not None and _apple_jwks_cache_expires and now < _apple_jwks_cache_expires:
        return _apple_jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(APPLE_JWKS_URL)
    resp.raise_for_status()
    data = resp.json()
    if "keys" not in data:
        raise ValueError("Apple JWKS response missing 'keys' field")
    _apple_jwks_cache = data["keys"]
    _apple_jwks_cache_expires = now + timedelta(hours=24)
    return _apple_jwks_cache


async def verify_apple_token(identity_token: str) -> dict:
    global _apple_jwks_cache, _apple_jwks_cache_expires
    try:
        header = jwt.get_unverified_header(identity_token)
    except jwt.PyJWTError as exc:
        raise ValueError("Malformed Apple identity token") from exc

    kid = header.get("kid")

    keys = await _get_apple_jwks()
    key_data = next((k for k in keys if k["kid"] == kid), None)

    if key_data is None:
        _apple_jwks_cache = None
        _apple_jwks_cache_expires = None
        keys = await _get_apple_jwks()
        key_data = next((k for k in keys if k["kid"] == kid), None)

    if key_data is None:
        raise ValueError(f"Unknown Apple key ID: {kid}")

    public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
    bundle_id = os.environ["APPLE_BUNDLE_ID"]

    try:
        return jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=bundle_id,
            issuer="https://appleid.apple.com",
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid Apple identity token") from exc


def _create_exchange_code(jwt_token: str) -> str:
    code = secrets.token_urlsafe(32)
    _exchange_codes[code] = (jwt_token, datetime.now(timezone.utc) + timedelta(seconds=60))
    return code


def _consume_exchange_code(code: str) -> str | None:
    entry = _exchange_codes.pop(code, None)
    if entry is None:
        return None
    jwt_token, expires_at = entry
    if datetime.now(timezone.utc) > expires_at:
        return None
    return jwt_token


def generate_unique_username(db, base: str) -> str:
    if not db.query(User).filter(User.username == base).first():
        return base
    counter = 2
    while db.query(User).filter(User.username == f"{base}_{counter}").first():
        counter += 1
    return f"{base}_{counter}"


def _maybe_reactivate(user: User, db: Session) -> bool:
    if user.is_active or user.deletion_requested_at is None:
        return False
    deletion_time = user.deletion_requested_at
    if deletion_time.tzinfo is None:
        deletion_time = deletion_time.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - deletion_time <= timedelta(days=30):
        user.is_active = True
        user.deletion_requested_at = None
        db.commit()
        return True
    return False


@router.post("/token")
@limiter.limit("5/minute")
async def login_for_access_token(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = db.query(User).filter(
        or_(
            func.lower(User.username) == form_data.username.lower(),
            func.lower(User.email) == form_data.username.lower()
        )
    ).first()

    if not (user and verify_password(form_data.password, user.hashed_password)):
        raise UNAUTHORIZED_EXCEPTION

    if not user.is_active:
        if not _maybe_reactivate(user, db):
            raise INACTIVE_USER_EXCEPTION
        db.refresh(user)

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=TOKEN_EXPIRES_MINUTES)
    )

    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        max_age=TOKEN_EXPIRES_MINUTES * 60,
    )
    return response


@router.post("/refresh", responses={401: {"description": "No access token found or invalid/expired."}})
async def refresh_token(
        db: Annotated[Session, Depends(get_db)],
        access_token: Annotated[Optional[str], Cookie] = None,
        authorization: Annotated[Optional[str], Header()] = None,
):
    # Accept token from cookie (web) or Authorization header (mobile)
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    if not token:
        raise HTTPException(
            status_code=401,
            detail="No access token found"
        )

    try:
        token_data = verify_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    # Get the user from database
    user = db.query(User).filter(User.username == token_data.username).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User account is inactive"
        )

    new_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=TOKEN_EXPIRES_MINUTES)
    )

    response = JSONResponse(content={
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRES_MINUTES * 60
    })

    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        max_age=TOKEN_EXPIRES_MINUTES * 60,
    )

    return response


@router.get("/verify", responses={401: {"description": "No access token found or invalid/expired."}})
async def verify_token_endpoint(
        access_token: Annotated[Optional[str], Cookie] = None
):
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="No access token found"
        )

    try:
        token_data = verify_access_token(access_token)

        return {
            "valid": True,
            "username": token_data.username,
            "expires_at": datetime.fromtimestamp(token_data.exp,
                                                 tz=timezone.utc).isoformat() if token_data.exp else None
        }
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


@router.get("/oauth/google", tags=["oauth"])
def google_login(request: Request):
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]

    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={state}"
    )

    return RedirectResponse(url=google_auth_url)


@router.get("/oauth/google/callback",
            responses={400: {"description": "Google token exchange failed, email not verified, or missing user data."}})
async def google_callback(
        code: str,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        state: Optional[str] = None,
):
    expected_state = request.session.pop("oauth_state", None)
    if not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
            },
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Google token exchange failed")

    access_token = token_resp.json()["access_token"]

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    userinfo = userinfo_resp.json()

    if not userinfo.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email not verified")

    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    oauth_id = userinfo.get("sub")
    if not oauth_id:
        raise HTTPException(status_code=400, detail="Invalid Google Account ID")

    user = (
        db.query(User)
        .filter(
            User.oauth_provider == "google",
            User.oauth_id == oauth_id,
        )
        .first()
    )

    if user and not user.is_active:
        _maybe_reactivate(user, db)
        db.refresh(user)

    is_new_user = False

    if not user:
        is_new_user = True
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=userinfo.get("given_name") or "",
            lastname=userinfo.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=userinfo.get("picture"),
            country_of_origin=None,
            date_of_birth=None
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(data={"sub": user.username})

    redirect_url = os.environ["FRONTEND_URL"]

    if is_new_user:
        code = _create_exchange_code(jwt_token)
        response = RedirectResponse(url=f"{redirect_url}/complete-profile?code={code}")
    else:
        response = RedirectResponse(url=f"{redirect_url}")

    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        max_age=3600 * 24 * 7,
    )

    return response


@router.post("/exchange", responses={400: {"description": "Invalid or expired exchange code"}})
async def exchange_code(code: str):
    jwt_token = _consume_exchange_code(code)
    if not jwt_token:
        raise HTTPException(status_code=400, detail="Invalid or expired exchange code")

    response = JSONResponse(content={"access_token": jwt_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        max_age=3600 * 24 * 7,
    )
    return response


class GoogleTokenRequest(BaseModel):
    id_token: str


@router.post("/oauth/google/token", tags=["oauth"], responses={
    400: {"description": "Invalid Google ID token, audience mismatch, unverified email, or missing account data."}
})
async def google_token_exchange(
        payload: GoogleTokenRequest,
        db: Annotated[Session, Depends(get_db)],
):
    async with httpx.AsyncClient() as client:
        tokeninfo_resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": payload.id_token},
        )

    if tokeninfo_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid Google ID token")

    claims = tokeninfo_resp.json()

    expected_aud = os.environ.get("GOOGLE_CLIENT_ID")
    if claims.get("aud") != expected_aud:
        raise HTTPException(status_code=400, detail="Token audience mismatch")

    if str(claims.get("email_verified")).lower() != "true":
        raise HTTPException(status_code=400, detail="Google email not verified")

    email = claims.get("email")
    oauth_id = claims.get("sub")
    if not email or not oauth_id:
        raise HTTPException(status_code=400, detail="Missing required Google account data")

    user = db.query(User).filter(
        User.oauth_provider == "google",
        User.oauth_id == oauth_id,
    ).first()

    if user and not user.is_active:
        _maybe_reactivate(user, db)
        db.refresh(user)

    is_new_user = user is None

    if is_new_user:
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=claims.get("given_name") or "",
            lastname=claims.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=claims.get("picture"),
            country_of_origin=None,
            date_of_birth=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(data={"sub": user.username})

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
    }


class AppleTokenRequest(BaseModel):
    identity_token: str
    firstname: str = ""
    lastname: str = ""


@router.post("/oauth/apple/token", tags=["oauth"], responses={
    400: {"description": "Invalid identity token, audience mismatch, or email conflict."}
})
async def apple_token_exchange(
        payload: AppleTokenRequest,
        db: Annotated[Session, Depends(get_db)],
):
    try:
        claims = await verify_apple_token(payload.identity_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Apple identity token")

    sub = claims.get("sub")
    email = claims.get("email")

    if not sub or not email:
        raise HTTPException(status_code=400, detail="Missing required Apple account data")

    user = db.query(User).filter(
        User.oauth_provider == "apple",
        User.oauth_id == sub,
    ).first()

    if user and not user.is_active:
        _maybe_reactivate(user, db)
        db.refresh(user)

    is_new_user = user is None

    if is_new_user:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")

        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=payload.firstname,
            lastname=payload.lastname,
            created_at=datetime.now(timezone.utc),
            oauth_provider="apple",
            oauth_id=sub,
            avatar_url=None,
            country_of_origin=None,
            date_of_birth=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(data={"sub": user.username})

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
    }


@router.post("/logout", responses={200: {"description": "Logged out successfully"}})
async def logout():
    response = JSONResponse(content={
        "message": "Successfully logged out"
    })

    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None,
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="none" if IS_PRODUCTION else "lax"
    )

    return response


@router.get("/logout/redirect")
async def logout_redirect():
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    response = RedirectResponse(url=frontend_url)

    # Clear the cookie
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None,
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="none" if IS_PRODUCTION else "lax"
    )

    return response
