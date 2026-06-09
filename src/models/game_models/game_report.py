from pydantic import BaseModel

from src.models.enums.report_reason_enum import GameReportReasonEnum


class GameReportRequest(BaseModel):
    reason: GameReportReasonEnum


class GameReportResponse(BaseModel):
    message: str
