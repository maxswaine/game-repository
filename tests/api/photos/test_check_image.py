from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.moderation import check_image


def _client_with_categories(**flags):
    categories = SimpleNamespace(
        sexual=False, sexual_minors=False, violence_graphic=False,
        hate=False, hate_threatening=False,
    )
    for k, v in flags.items():
        setattr(categories, k, v)
    result = SimpleNamespace(categories=categories)
    response = SimpleNamespace(results=[result])
    client = MagicMock()
    client.moderations.create.return_value = response
    return client


def test_check_image_safe_returns_true():
    with patch("src.services.moderation.OpenAI", return_value=_client_with_categories()):
        assert check_image("https://cdn/x.jpg") is True


def test_check_image_flags_sexual_minors_returns_false():
    with patch("src.services.moderation.OpenAI", return_value=_client_with_categories(sexual_minors=True)):
        assert check_image("https://cdn/x.jpg") is False


def test_check_image_fails_closed_on_error():
    client = MagicMock()
    client.moderations.create.side_effect = RuntimeError("boom")
    with patch("src.services.moderation.OpenAI", return_value=client):
        assert check_image("https://cdn/x.jpg") is False
