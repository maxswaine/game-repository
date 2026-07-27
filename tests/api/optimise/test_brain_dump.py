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

from src.models.optimisation_models.optimisation_models import OptimisationResult


def _patch_split(result, missing, error):
    mock = MagicMock(return_value=(result, missing, error))
    return patch("src.api.optimisation.get_brain_dump_splitter", return_value=MagicMock(split=mock)), mock


def _optimised(text):
    return OptimisationResult(status="success", original=text, optimized=f"{text} (optimised)")


def _patch_optimiser(side_effect=_optimised):
    mock = MagicMock(side_effect=lambda text: side_effect(text))
    return patch(
        "src.api.optimisation.get_optimiser",
        return_value=MagicMock(optimise=mock),
    ), mock


def test_brain_dump_happy_path(client_with_auth):
    result = BrainDumpResult(objective="Win.", setup="Deal cards.", rules="Take turns.")
    split_ctx, _ = _patch_split(result, [], None)
    opt_ctx, opt_mock = _patch_optimiser()
    with patch("src.api.optimisation.check_content", return_value=True), split_ctx, opt_ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["objective"] == "Win. (optimised)"
    assert body["data"]["setup"] == "Deal cards. (optimised)"
    assert body["data"]["rules"] == "Take turns. (optimised)"
    assert body["missing_fields"] == []
    assert opt_mock.call_count == 3


def test_brain_dump_reports_missing(client_with_auth):
    result = BrainDumpResult(objective="Win.", setup="", rules="Take turns.")
    split_ctx, _ = _patch_split(result, ["setup"], None)
    opt_ctx, opt_mock = _patch_optimiser()
    with patch("src.api.optimisation.check_content", return_value=True), split_ctx, opt_ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["missing_fields"] == ["setup"]
    assert body["data"]["setup"] == ""
    # empty field must not be sent for optimisation
    assert opt_mock.call_count == 2


def test_brain_dump_optimise_failure_falls_back_to_raw(client_with_auth):
    result = BrainDumpResult(objective="Win.", setup="Deal cards.", rules="Take turns.")
    split_ctx, _ = _patch_split(result, [], None)

    def side_effect(text):
        if text == "Deal cards.":
            return OptimisationResult(status="failed", original=text, optimized=text, note="boom")
        return _optimised(text)

    opt_ctx, _ = _patch_optimiser(side_effect=side_effect)
    with patch("src.api.optimisation.check_content", return_value=True), split_ctx, opt_ctx:
        response = client_with_auth.post(
            "/optimise/brain-dump",
            json={"dump_text": "a nice long description of a card game here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["objective"] == "Win. (optimised)"
    assert body["data"]["setup"] == "Deal cards."
    assert body["data"]["rules"] == "Take turns. (optimised)"


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
