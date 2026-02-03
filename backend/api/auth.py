import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from backend.core.exceptions import UNAUTHORIZED_EXCEPTION, INACTIVE_USER_EXCEPTION
from backend.core.security import create_access_token
from backend.core.security import verify_password, TOKEN_EXPIRES_MINUTES
from backend.db.database import get_db
from backend.db.tables import User

router = APIRouter(prefix="/auth")


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not (user and verify_password(form_data.password, user.hashed_password)):
        raise UNAUTHORIZED_EXCEPTION

    if not user.is_active:
        raise INACTIVE_USER_EXCEPTION

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=TOKEN_EXPIRES_MINUTES
    )
    return {"access_token": access_token, "token_type": "bearer"}


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


@router.get("/callback")
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
    if not user:
        user = User(
            email=email,
            username=email.split("@")[0],
            firstname=userinfo.get("given_name"),
            lastname=userinfo.get("family_name"),
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=userinfo.get("picture"),
            country_of_origin="GB"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(data={"sub": user.username})

    redirect_url = os.environ["FRONTEND_URL"]
    response = RedirectResponse(url=f"{redirect_url}/docs", )

    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=os.getenv("ENV") == "production",
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax",
        max_age=3600 * 24 * 7,
    )

    return response
