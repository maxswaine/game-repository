from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.core.exceptions import USER_NOT_FOUND_EXCEPTION, INACTIVE_USER_EXCEPTION, UNAUTHORIZED_EXCEPTION
from backend.core.security import verify_access_token, hash_password
from backend.db.database import get_db
from backend.db.tables import User
from backend.models.user import UserCreate, UserPublicRead, UserPrivateRead

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
    user = db.query(User).filter(User.username == token_data.username).first()

    if not user:
        raise USER_NOT_FOUND_EXCEPTION

    return user


def get_current_user_optional(
        token: str | None = Depends(get_access_token),
        db: Session = Depends(get_db),
):
    if not token:
        return None
    try:
        token_data = verify_access_token(token)
        return db.query(User).filter(User.username == token_data.username).first()
    except HTTPException:
        return None


def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise INACTIVE_USER_EXCEPTION
    return current_user


# CREATE
@router.post("/register", response_model=UserPublicRead, status_code=201)
def create_new_user(new_user: UserCreate, db: Session = Depends(get_db)):
    print(f"Received user data: {new_user}")

    try:
        if db.query(User).filter(User.username == new_user.username).first():
            raise HTTPException(status_code=400, detail="Username taken")
        if db.query(User).filter(User.email == new_user.email).first():
            raise HTTPException(status_code=400, detail="User already registered with this email")

        hashed_password = hash_password(new_user.password)
        db_new_user = User(
            firstname=new_user.firstname,
            lastname=new_user.lastname,
            email=new_user.email,
            username=new_user.username,
            hashed_password=hashed_password,
            country_of_origin=new_user.country_of_origin
        )
        db.add(db_new_user)
        db.commit()
        db.refresh(db_new_user)
        return db_new_user
    except Exception as e:
        print(f"Registration error: {type(e).__name__}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")


# READ
@router.get("/me", response_model=UserPrivateRead, status_code=200)
def get_current_user(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)):
    if not current_user:
        raise UNAUTHORIZED_EXCEPTION
    return db.query(User).filter(User.id == current_user.id).first()


@router.get("/all", response_model=List[UserPrivateRead], status_code=200)
def get_all_users(
        db: Session = Depends(get_db),
        limit: int = 20,
        offset: int = 0
):
    return db.query(User).all()

# UPDATE
# DELETE
@router.delete("/{user_id}", status_code=204)
def delete_account(
        user_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    if str(current_user.id) != str(user_id):
        raise HTTPException(status_code=403, detail="Not allowed to delete this account")

    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise USER_NOT_FOUND_EXCEPTION

    db.delete(user)
    db.commit()
    return {"message": "Account successfully deleted"}
