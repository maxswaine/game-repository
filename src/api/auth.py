# src/api/auth.py
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Cookie, Header, Request
from fastapi.security import OAuth2PasswordRequestForm
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


def generate_unique_username(db, base: str) -> str:
    if not db.query(User).filter(User.username == base).first():
        return base
    counter = 2
    while db.query(User).filter(User.username == f"{base}_{counter}").first():
        counter += 1
    return f"{base}_{counter}"


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
        raise INACTIVE_USER_EXCEPTION

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

    is_new_user = False

    if not user:
        is_new_user = True
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=userinfo.get("given_name"),
            lastname=userinfo.get("family_name"),
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
        response = RedirectResponse(url=f"{redirect_url}/complete-profile")
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
