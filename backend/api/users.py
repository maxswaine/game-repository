from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.core.exceptions import NOT_FOUND_EXCEPTION, INACTIVE_USER_EXCEPTION, FORBIDDEN_EXCEPTION
from backend.core.security import verify_access_token, hash_password
from backend.db.database import get_db
from backend.db.tables import User
from backend.models.user import UserCreate, UserPublicRead, UserPrivateRead

router = APIRouter()

# Security Config
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token_data = verify_access_token(token)
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        raise NOT_FOUND_EXCEPTION
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise INACTIVE_USER_EXCEPTION
    return current_user


# CREATE
@router.post("/register", response_model=UserPublicRead, status_code=201)
def create_new_user(new_user: UserCreate, db: Session = Depends(get_db)):
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


# READ
@router.get("/me", response_model=UserPrivateRead, status_code=200)
def get_current_user(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)):
    if not current_user:
        raise FORBIDDEN_EXCEPTION
    return db.query(User).filter(User.id == current_user.id).first()

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
        raise NOT_FOUND_EXCEPTION

    db.delete(user)
    db.commit()
    return {"message": "Account successfully deleted"}
