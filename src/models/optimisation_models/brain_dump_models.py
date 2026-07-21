from typing import Optional

from pydantic import BaseModel, Field


class BrainDumpRequest(BaseModel):
    dump_text: str = Field(
        ...,
        max_length=4000,
        description="Freeform text describing the game, to be split into fields",
    )


class BrainDumpResult(BaseModel):
    objective: str = Field(default="", description="Extracted objective, empty if absent")
    setup: str = Field(default="", description="Extracted setup, empty if absent")
    rules: str = Field(default="", description="Extracted rules, empty if absent")


class BrainDumpResponse(BaseModel):
    success: bool = Field(..., description="Whether the split succeeded")
    data: Optional[BrainDumpResult] = Field(None, description="The three split fields if successful")
    missing_fields: list[str] = Field(
        default_factory=list, description="Which of objective/setup/rules came back empty"
    )
    error_message: Optional[str] = Field(None, description="Reason when success is false")
