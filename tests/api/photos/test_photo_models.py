from src.models.game_models.game_photo import (
    PhotoUploadUrlRequest,
    PhotoUploadUrlResponse,
    PhotoRegisterRequest,
    PhotoReorderRequest,
    GamePhotoRead,
)


def test_photo_models_construct():
    assert PhotoUploadUrlRequest(content_type="image/jpeg").content_type == "image/jpeg"
    resp = PhotoUploadUrlResponse(upload_url="https://u", object_key="games/g/a.jpg")
    assert resp.object_key == "games/g/a.jpg"
    assert PhotoRegisterRequest(object_key="games/g/a.jpg").object_key == "games/g/a.jpg"
    assert PhotoReorderRequest(photo_ids=["1", "2"]).photo_ids == ["1", "2"]
    read = GamePhotoRead(id="1", public_url="https://cdn/a.jpg", position=0)
    assert read.position == 0
