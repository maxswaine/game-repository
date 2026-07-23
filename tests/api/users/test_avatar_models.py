from src.models.user_models.avatar import (
    AvatarUploadUrlRequest,
    AvatarUploadUrlResponse,
    AvatarRegisterRequest,
)


def test_avatar_models_construct():
    assert AvatarUploadUrlRequest(content_type="image/jpeg").content_type == "image/jpeg"
    resp = AvatarUploadUrlResponse(upload_url="https://u", object_key="users/u1/a.jpg")
    assert resp.object_key == "users/u1/a.jpg"
    assert AvatarRegisterRequest(object_key="users/u1/a.jpg").object_key == "users/u1/a.jpg"
