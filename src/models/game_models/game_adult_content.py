from pydantic import BaseModel


class GameAdultContent(BaseModel):
    has_adult_content: bool
