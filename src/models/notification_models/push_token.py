from pydantic import BaseModel


class PushTokenCreate(BaseModel):
    token: str
    platform: str


class PushTokenDelete(BaseModel):
    token: str
