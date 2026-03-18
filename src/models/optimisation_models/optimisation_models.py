# src/schemas/optimisation_models.py
from typing import Optional

from pydantic import BaseModel, Field


class OptimisationRequest(BaseModel):
    field_type: str = Field(..., description="Type of game element (objective, setup, rules)")
    original_text: str = Field(..., min_length=10, description="The raw text from the user")


class OptimisationResult(BaseModel):
    status: str = Field(default="success", description="Status of the operation (success/failed)")
    original: str = Field(..., description="The original input text")
    optimized: str = Field(..., description="The AI-generated optimized text")
    char_count_saved: Optional[int] = Field(None, description="Difference in character count")
    note: Optional[str] = Field(None, description="Error message or note if optimization was skipped/failed")


class OptimisationResponse(BaseModel):
    success: bool = Field(..., description="Whether the optimization succeeded")
    data: Optional[OptimisationResult] = Field(None, description="The result object if successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
