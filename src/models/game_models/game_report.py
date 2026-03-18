from pydantic import BaseModel


class GameReportRequest(BaseModel):
    message: str


class GameReportResponse(GameReportRequest):
    pass
