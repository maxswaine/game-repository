from fastapi import HTTPException
from starlette import status

FORBIDDEN_EXCEPTION = HTTPException(
                status_code= status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
NOT_FOUND_EXCEPTION = HTTPException(
                status_code= status.HTTP_404_NOT_FOUND,
                detail="User does not exist",
                headers={"WWW-Authenticate": "Bearer"}
            )

INACTIVE_USER_EXCEPTION = HTTPException(
            status_code=400,
            detail="User is currently inactive"
        )