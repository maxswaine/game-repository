from __future__ import annotations

from datetime import datetime
from typing import Optional

import pycountry
from pydantic import ConfigDict, BaseModel, field_validator

date_of_birth_error = 'date_of_birth must be in YYYY-MM-DD format'


class UserBase(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    hashed_password: str
    country_of_origin: str
    date_of_birth: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_updated: datetime


class UserCreate(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    password: str
    country_of_origin: str
    date_of_birth: Optional[str] = None

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(date_of_birth_error)
        return v

    @field_validator('country_of_origin')
    @classmethod
    def validate_country(cls, v):
        if v is None:
            return v

        v = v.upper()

        try:
            pycountry.countries.get(alpha_2=v)
        except (KeyError, AttributeError):
            raise ValueError(f'Invalid country code: {v}. Must be a valid ISO 3166-1 alpha-2 code')

        return v


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


class UserFavouriteBase(BaseModel):
    user_id: str
    game_id: str
    created_at: datetime


class UserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    country_of_origin: Optional[str] = None
    date_of_birth: Optional[str] = None
    avatar_url: Optional[str] = None

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(date_of_birth_error)
        return v


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserCompleteProfile(BaseModel):
    """For OAuth users completing their profile after signup"""
    date_of_birth: str
    country_of_origin: str

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(date_of_birth_error)
        return v