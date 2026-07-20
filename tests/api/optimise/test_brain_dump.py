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
