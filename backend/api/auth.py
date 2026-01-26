from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.core.exceptions import FORBIDDEN_EXCEPTION, INACTIVE_USER_EXCEPTION
from backend.core.security import verify_password, create_access_token, TOKEN_EXPIRES
from backend.db.database import get_db
from backend.db.tables import User

router = APIRouter()

@router.post("/auth/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not (user and verify_password(form_data.password, user.hashed_password)):
        raise FORBIDDEN_EXCEPTION

    if not user.is_active:
        raise INACTIVE_USER_EXCEPTION

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=TOKEN_EXPIRES
    )
    return {"access_token": access_token, "token_type": "bearer"}
