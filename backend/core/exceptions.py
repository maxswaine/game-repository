from fastapi import HTTPException
from starlette import status

UNAUTHORIZED_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"}
)

USER_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="User does not exist",
    headers={"WWW-Authenticate": "Bearer"}
)

FORBIDDEN_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="User does not have the required permissions",
    headers={"WWW-Authenticate": "Bearer"}
)

INACTIVE_USER_EXCEPTION = HTTPException(
    status_code=400,
    detail="User is currently inactive"
)

GAME_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=404,
    detail="Game not found"
)
