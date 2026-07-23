from pydantic import BaseModel


class AvatarUploadUrlRequest(BaseModel):
    content_type: str


class AvatarUploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str


class AvatarRegisterRequest(BaseModel):
    object_key: str
