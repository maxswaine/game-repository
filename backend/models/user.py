from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, BaseModel

class UserBase(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    hashed_password: str
    country_of_origin: str
    role: str
    is_active: bool
    created_at: datetime

class UserCreate(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    password: str
    country_of_origin: str

class UserPublicRead(BaseModel):
    username: str
    country_of_origin: str
    model_config = ConfigDict(from_attributes=True)

class UserPrivateRead(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    country_of_origin: str

class UserLogin(BaseModel):
    username: str
    password: str
