from src.models.optimisation_models.brain_dump_models import (
    BrainDumpRequest,
    BrainDumpResult,
    BrainDumpResponse,
)


def test_brain_dump_models_construct():
    req = BrainDumpRequest(dump_text="roll dice, first to empty their hand wins")
    assert req.dump_text.startswith("roll dice")

    result = BrainDumpResult(objective="Win by emptying your hand.", setup="", rules="Roll and play.")
    resp = BrainDumpResponse(
        success=True, data=result, missing_fields=["setup"], error_message=None
    )
    assert resp.success is True
    assert resp.data.setup == ""
    assert resp.missing_fields == ["setup"]
    assert resp.error_message is None


from unittest.mock import MagicMock, patch  # noqa: E402


def _patch_split(result, missing, error):
    mock = MagicMock(return_value=(result, missing, error))
    return patch("src.api.optimisation.get_brain_dump_splitter", return_value=MagicMock(split=mock)), mock


def test_brain_dump_happy_path(client_with_auth):
    result = BrainDumpResult(objective="Win.", setup="Deal cards.", rules="Take turns.")
    ctx, split_mock = _patch_split(result, [], None)
    with patch("src.api.optimisation.check_content", return_value=True), ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["objective"] == "Win."
    assert body["missing_fields"] == []


def test_brain_dump_reports_missing(client_with_auth):
    result = BrainDumpResult(objective="Win.", setup="", rules="Take turns.")
    ctx, _ = _patch_split(result, ["setup"], None)
    with patch("src.api.optimisation.check_content", return_value=True), ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    assert response.json()["missing_fields"] == ["setup"]


def test_brain_dump_too_short_does_not_call_openai(client_with_auth):
    ctx, split_mock = _patch_split(None, [], None)
    with patch("src.api.optimisation.check_content", return_value=True), ctx:
        response = client_with_auth.post("/optimise/brain-dump", json={"dump_text": "too short"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "short" in body["error_message"].lower()
    split_mock.assert_not_called()


def test_brain_dump_moderation_blocked(client_with_auth):
    with patch("src.api.optimisation.check_content", return_value=False):
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description that trips moderation here"},
        )
    assert response.status_code == 422
    assert "community guidelines" in response.json()["detail"].lower()


def test_brain_dump_too_long_rejected(client_with_auth):
    response = client_with_auth.post(
        "/optimise/brain-dump", json={"dump_text": "x" * 4001}
    )
    assert response.status_code == 422


def test_brain_dump_openai_failure_falls_back(client_with_auth):
    ctx, _ = _patch_split(None, [], "Brain dump failed, please enter fields manually.")
    with patch("src.api.optimisation.check_content", return_value=True), ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert "manually" in body["error_message"].lower()


def test_brain_dump_requires_auth(client_no_auth):
    response = client_no_auth.post(
        "/optimise/brain-dump",
        json={"dump_text": "a nice long description of a card game here"},
    )
    assert response.status_code == 401
