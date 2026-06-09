from unittest.mock import patch, MagicMock

from src.models.optimisation_models.optimisation_models import OptimisationResult


def test_optimise_hate_content_blocked(client_with_auth):
    with patch("src.api.optimisation.check_content", return_value=False):
        response = client_with_auth.post("/optimise/", json={
            "field_type": "description",
            "original_text": "some text that would be flagged by moderation"
        })
    assert response.status_code == 422
    assert "community guidelines" in response.json()["detail"].lower()


def test_optimise_clean_content_passes_moderation(client_with_auth):
    _result = OptimisationResult(
        status="success",
        original="A fun card game",
        optimized="An engaging card game for groups",
    )
    with patch("src.api.optimisation.check_content", return_value=True), \
         patch("src.services.optimiser.TextOptimiser.optimise", return_value=_result):
        response = client_with_auth.post("/optimise/", json={
            "field_type": "description",
            "original_text": "A fun card game"
        })
    assert response.status_code == 200
    assert response.json()["success"] is True
