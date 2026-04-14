# src/api/users.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.exceptions import USER_NOT_FOUND_EXCEPTION, INACTIVE_USER_EXCEPTION, UNAUTHORIZED_EXCEPTION
from src.core.security import verify_access_token, hash_password, verify_password
from src.db.database import get_db
from src.db.tables import User
from src.models.user_models.user import UserCreate, UserPublicRead, UserPrivateRead, UserCompleteProfile, UserUpdate, \
    UserPasswordUpdate


class MessageResponse(BaseModel):
    message: str


router = APIRouter()

# Security Config
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_access_token(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
) -> str | None:
    if token:
        return token

    return request.cookies.get("access_token")


def get_current_user(
        token: str = Depends(get_access_token),
        db: Session = Depends(get_db),
):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_data = verify_access_token(token)
    user = db.query(User).filter(func.lower(User.username) == token_data.username.lower()).first()

    if not user:
        raise USER_NOT_FOUND_EXCEPTION

    return user


def get_current_user_optional(
        db: Annotated[Session, Depends(get_db)],
        token: str | None = Depends(get_access_token),
):
    if not token:
        return None
    try:
        token_data = verify_access_token(token)
        return db.query(User).filter(func.lower(User.username) == token_data.username.lower()).first()
    except HTTPException:
        return None


def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise INACTIVE_USER_EXCEPTION
    return current_user


# CREATE
@router.post("/register", response_model=UserPublicRead, status_code=201,
             responses={400: {"description": "Username taken or Email already in use"},
                        422: {"description": "Validation error: Invalid input data"},
                        500: {"description": "Internal Database error occurred"}}
             )
def create_new_user(
        db: Annotated[Session, Depends(get_db)],
        new_user: UserCreate,
):
    try:
        if db.query(User).filter(func.lower(User.username) == new_user.username.lower()).first():
            raise HTTPException(status_code=400, detail="Username taken")
        if db.query(User).filter(func.lower(User.email) == new_user.email.lower()).first():
            raise HTTPException(status_code=400, detail="User already registered with this email")

        hashed_password = hash_password(new_user.password)
        db_new_user = User(
            firstname=new_user.firstname,
            lastname=new_user.lastname,
            email=new_user.email,
            username=new_user.username,
            hashed_password=hashed_password,
            date_of_birth=new_user.date_of_birth,
            country_of_origin=new_user.country_of_origin
        )
        db.add(db_new_user)
        db.commit()
        db.refresh(db_new_user)
        return db_new_user
    except Exception as e:
        print(f"Registration error: {type(e).__name__}: {str(e)}")
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")


@router.post("/me/complete-profile", response_model=UserPrivateRead, status_code=200,
             responses={401: {"description": "Authentication required"},
                        400: {"description": "Profile already complete"}})
def complete_profile(
        db: Annotated[Session, Depends(get_db)],
        profile_data: UserCompleteProfile,
        current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user


# READ
@router.get("/me", response_model=UserPrivateRead, status_code=200)
def get_me(
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)],
):
    if not current_user:
        raise UNAUTHORIZED_EXCEPTION
    return db.query(User).filter(User.id == current_user.id).first()


# UPDATE
@router.patch("/me", response_model=UserPrivateRead, status_code=200,
              responses={400: {"description": "Email already in use exception"}})
def update_my_profile(
        updates: UserUpdate,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)],
):
    update_data = updates.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing_user = db.query(User).filter(
            User.email == update_data["email"],
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Email already in use"
            )

    for key, value in update_data.items():
        if value is not None:
            setattr(current_user, key, value)

    current_user.last_updated = datetime.now(timezone.utc)

    db.commit()
    db.refresh(current_user)

    return current_user


@router.patch("/me/password", status_code=200, responses={
    400: {"description": "Unable to change current password"},
})
def update_my_password(
        password_update: UserPasswordUpdate,
        db: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User, Depends(get_current_active_user)],
):
    if current_user.oauth_provider:
        raise HTTPException(
            status_code=400,
            detail="Cannot change password for OAuth accounts"
        )

    if not verify_password(password_update.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect"
        )

    current_user.hashed_password = hash_password(password_update.new_password)
    current_user.last_updated = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Password updated successfully"}


# DELETE
@router.delete("/{user_id}", status_code=204, responses={
    403: {"description": "Not allowed to delete someone else's account"}
})
def delete_account(
        user_id: str,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)]
):
    if str(current_user.id) != str(user_id):
        raise HTTPException(status_code=403, detail="Not allowed to delete this account")

    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise USER_NOT_FOUND_EXCEPTION

    db.delete(user)
    db.commit()
    return {"message": "Account successfully deleted"}
