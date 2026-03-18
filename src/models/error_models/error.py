# src/models/error_models/error.py - SHOULD BE THIS FOR BEST PRACTICE
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    message: str = Field(..., description="Error message")
    detail: str = Field(..., description="Additional error details")

# For 422 validation errors specifically, use this structure in responses
