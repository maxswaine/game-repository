from pydantic import BaseModel, ConfigDict


class PhotoUploadUrlRequest(BaseModel):
    content_type: str


class PhotoUploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str


class PhotoRegisterRequest(BaseModel):
    object_key: str


class PhotoReorderRequest(BaseModel):
    photo_ids: list[str]


class GamePhotoRead(BaseModel):
    id: str
    public_url: str
    position: int

    model_config = ConfigDict(from_attributes=True)
