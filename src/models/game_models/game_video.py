from pydantic import BaseModel, ConfigDict


class VideoUploadUrlRequest(BaseModel):
    content_type: str


class VideoUploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str


class VideoRegisterRequest(BaseModel):
    object_key: str


class GameVideoRead(BaseModel):
    id: str
    public_url: str

    model_config = ConfigDict(from_attributes=True)
