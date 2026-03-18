from pydantic import BaseModel


class GameVisibility(BaseModel):
    is_public: bool
