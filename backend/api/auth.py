import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, JSONResponse

from backend.core.exceptions import UNAUTHORIZED_EXCEPTION, INACTIVE_USER_EXCEPTION
from backend.core.security import create_access_token, verify_access_token
from backend.core.security import verify_password, TOKEN_EXPIRES_MINUTES
from backend.db.database import get_db
from backend.db.tables import User

router = APIRouter(prefix="/auth")


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh_token(
        access_token: Optional[str] = Cookie(None),
        db: Session = Depends(get_db)
):
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="No access token found"
        )

    try:
        payload = verify_access_token(access_token)
        username = payload.get("sub")

        if username is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    # Get the user from database
    user = db.query(User).filter(User.username == username).first()

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
        secure=os.getenv("ENV") == "production",
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax",
        max_age=TOKEN_EXPIRES_MINUTES * 60,
    )

    return response


@router.get("/verify")
async def verify_token_endpoint(
        access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="No access token found"
        )

    try:
        payload = verify_access_token(access_token)
        username = payload.get("sub")
        exp = payload.get("exp")

        if username is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        return {
            "valid": True,
            "username": username,
            "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        }
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


@router.get("/oauth/google", tags=["oauth"])
def google_login():
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=consent"
    )

    return RedirectResponse(url=google_auth_url)


@router.get("/oauth/google/callback")
async def google_callback(
        code: str,
        db: Session = Depends(get_db),
):
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
            username=email.split("@")[0],
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
        response = RedirectResponse(url=f"{redirect_url}/docs")

    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=os.getenv("ENV") == "production",
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax",
        max_age=3600 * 24 * 7,
    )

    return response


@router.post("/logout")
async def logout():
    response = JSONResponse(content={
        "message": "Successfully logged out"
    })

    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None,
        secure=os.getenv("ENV") == "production",
        httponly=True,
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax"
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
        secure=os.getenv("ENV") == "production",
        httponly=True,
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax"
    )

    return response
