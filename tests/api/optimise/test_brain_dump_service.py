import json
from unittest.mock import MagicMock, patch

from src.services.brain_dump import BrainDumpSplitter


def _fake_client(output_json: str):
    client = MagicMock()
    client.responses.create.return_value = MagicMock(output_text=output_json)
    return client


def test_split_populates_all_fields():
    payload = json.dumps({
        "objective": "Be first to empty your hand.",
        "setup": "Deal 7 cards each.",
        "rules": "On your turn, play a matching card.",
    })
    with patch("src.services.brain_dump._get_client", return_value=_fake_client(payload)):
        result, missing, error = BrainDumpSplitter().split("some long enough dump text here")

    assert error is None
    assert missing == []
    assert result.objective == "Be first to empty your hand."
    assert result.setup == "Deal 7 cards each."
    assert result.rules == "On your turn, play a matching card."


def test_split_reports_missing_field():
    payload = json.dumps({
        "objective": "Be first to empty your hand.",
        "setup": "",
        "rules": "Play a matching card.",
    })
    with patch("src.services.brain_dump._get_client", return_value=_fake_client(payload)):
        result, missing, error = BrainDumpSplitter().split("some long enough dump text here")

    assert error is None
    assert missing == ["setup"]
    assert result.setup == ""


def test_split_handles_openai_failure():
    client = MagicMock()
    client.responses.create.side_effect = RuntimeError("boom")
    with patch("src.services.brain_dump._get_client", return_value=client):
        result, missing, error = BrainDumpSplitter().split("some long enough dump text here")

    assert result is None
    assert missing == []
    assert error is not None
