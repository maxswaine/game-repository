# Brain Dump Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /optimise/brain-dump` endpoint that splits one freeform game description into `objective`, `setup`, and `rules` using an OpenAI call, returning a non-persisted draft the frontend pre-fills into the create-game form.

**Architecture:** Reuse the existing optimiser plumbing (auth dependency, moderation, OpenAI client pattern). A new stateless `BrainDumpSplitter` service makes one `gpt-4.1-mini` call with JSON-schema structured output, parses the three fields, and computes which came back empty. A thin route in the existing optimisation router validates input (length, moderation) and wraps the result.

**Tech Stack:** FastAPI, Pydantic, OpenAI Python SDK (`responses.create`), pytest with SQLite test DB and mocked OpenAI.

## Global Constraints

- Model: **`gpt-4.1-mini`** (not nano). Temperature **0.2**.
- Structured output: OpenAI **JSON schema** (`strict`), keys exactly `objective`, `setup`, `rules`, each a string.
- Fields extracted: **only** `objective`, `setup`, `rules`. Never invent content; empty string when absent.
- Endpoint: **`POST /optimise/brain-dump`**, **auth required** (same dependency as `POST /optimise/`).
- Internal name stays **`brain_dump`** (endpoint path, module, class). UI button label is a frontend concern.
- Length bounds: min **20** chars (after strip) → graceful `success=false`; max **4000** chars → `422`.
- Non-persisted: the endpoint never creates or mutates a game.
- Tests run against SQLite: prefix pytest with `DATABASE_URL="sqlite:///./test.db"`. **Mock the OpenAI call — no live API in tests.**
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed
  ```

---

## File Structure

- **Create** `src/models/optimisation_models/brain_dump_models.py` — `BrainDumpRequest`, `BrainDumpResult`, `BrainDumpResponse`.
- **Modify** `src/utils/prompts.py` — add `BRAIN_DUMP_PROMPT` constant.
- **Create** `src/services/brain_dump.py` — `BrainDumpSplitter`, `get_brain_dump_splitter()`, `MIN_DUMP_LENGTH`, `FIELDS`.
- **Modify** `src/api/optimisation.py` — add the `/brain-dump` route + `MAX_DUMP_LENGTH`.
- **Create** `tests/api/optimise/test_brain_dump.py` — endpoint tests (mocked OpenAI + moderation).
- **Create** `tests/api/optimise/__init__.py` — only if it does not already exist.

---

## Task 1: Pydantic models

**Files:**
- Create: `src/models/optimisation_models/brain_dump_models.py`
- Test: `tests/api/optimise/test_brain_dump.py` (created here, extended in Task 3)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `BrainDumpRequest(dump_text: str)` — `dump_text` has `max_length=4000`.
  - `BrainDumpResult(objective: str, setup: str, rules: str)`.
  - `BrainDumpResponse(success: bool, data: BrainDumpResult | None, missing_fields: list[str], error_message: str | None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/api/optimise/test_brain_dump.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump.py::test_brain_dump_models_construct -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.optimisation_models.brain_dump_models'`

- [ ] **Step 3: Write minimal implementation**

Create `src/models/optimisation_models/brain_dump_models.py`:

```python
from typing import Optional

from pydantic import BaseModel, Field


class BrainDumpRequest(BaseModel):
    dump_text: str = Field(
        ...,
        max_length=4000,
        description="Freeform text describing the game, to be split into fields",
    )


class BrainDumpResult(BaseModel):
    objective: str = Field(default="", description="Extracted objective, empty if absent")
    setup: str = Field(default="", description="Extracted setup, empty if absent")
    rules: str = Field(default="", description="Extracted rules, empty if absent")


class BrainDumpResponse(BaseModel):
    success: bool = Field(..., description="Whether the split succeeded")
    data: Optional[BrainDumpResult] = Field(None, description="The three split fields if successful")
    missing_fields: list[str] = Field(
        default_factory=list, description="Which of objective/setup/rules came back empty"
    )
    error_message: Optional[str] = Field(None, description="Reason when success is false")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump.py::test_brain_dump_models_construct -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/models/optimisation_models/brain_dump_models.py tests/api/optimise/test_brain_dump.py
git commit -m "$(cat <<'EOF'
feat(brain-dump): add request/result/response models

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed
EOF
)"
```

---

## Task 2: Prompt + splitter service

**Files:**
- Modify: `src/utils/prompts.py` (append `BRAIN_DUMP_PROMPT`)
- Create: `src/services/brain_dump.py`
- Test: `tests/api/optimise/test_brain_dump_service.py`

**Interfaces:**
- Consumes: `BrainDumpResult` from Task 1; `BRAIN_DUMP_PROMPT` (added here).
- Produces:
  - `MIN_DUMP_LENGTH: int = 20`
  - `FIELDS: tuple[str, str, str] = ("objective", "setup", "rules")`
  - `class BrainDumpSplitter` with `split(dump_text: str) -> tuple[BrainDumpResult | None, list[str], str | None]` returning `(result, missing_fields, error_message)`. On success: `(result, missing, None)`. On any OpenAI/parse failure: `(None, [], error_message)`.
  - `get_brain_dump_splitter() -> BrainDumpSplitter` (cached singleton, mirrors `get_optimiser`).
  - `_get_client() -> OpenAI` (module-level; test patches this).

- [ ] **Step 1: Write the failing test**

Create `tests/api/optimise/test_brain_dump_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.brain_dump'`

- [ ] **Step 3a: Append the prompt template**

Append to the `PROMPT_TEMPLATES` file `src/utils/prompts.py` (after the closing `}` of `PROMPT_TEMPLATES`, as a new top-level constant):

```python

BRAIN_DUMP_PROMPT = """
### ROLE & GOAL
You are helping a user submit a game to What's That Game. You are given one freeform blob of text describing a game. Split it into exactly three fields: objective, setup, and rules.

### FIELD DEFINITIONS
- objective: what a player is trying to achieve / the win condition.
- setup: what must be prepared before play begins (deal cards, arrange the board, form teams).
- rules: how the game is actually played turn to turn.

### STRICT RULES
1. Use ONLY information present in the input. Do NOT invent objectives, setup steps, or rules.
2. If the input does not describe a field, return an EMPTY STRING "" for that field. An empty field is correct and expected — never pad it to look complete.
3. Do NOT move unrelated content into a field just to avoid leaving it empty.
4. Keep the user's wording where reasonable; lightly tidy grammar only.
5. Do NOT use Markdown code blocks or em dashes.
"""
```

- [ ] **Step 3b: Write the splitter service**

Create `src/services/brain_dump.py`:

```python
import json
import os

from openai import OpenAI

from src.models.optimisation_models.brain_dump_models import BrainDumpResult
from src.utils.prompts import BRAIN_DUMP_PROMPT

MIN_DUMP_LENGTH = 20
FIELDS = ("objective", "setup", "rules")

_SCHEMA = {
    "type": "object",
    "properties": {
        "objective": {"type": "string"},
        "setup": {"type": "string"},
        "rules": {"type": "string"},
    },
    "required": ["objective", "setup", "rules"],
    "additionalProperties": False,
}


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)


class BrainDumpSplitter:
    def split(self, dump_text: str) -> tuple[BrainDumpResult | None, list[str], str | None]:
        messages = [
            {"role": "system", "content": BRAIN_DUMP_PROMPT},
            {"role": "user", "content": f"Input: {dump_text}"},
        ]
        try:
            response = _get_client().responses.create(
                model="gpt-4.1-mini",
                input=messages,
                temperature=0.2,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "brain_dump_split",
                        "schema": _SCHEMA,
                        "strict": True,
                    }
                },
            )
            parsed = json.loads(response.output_text)
            result = BrainDumpResult(
                objective=(parsed.get("objective") or "").strip(),
                setup=(parsed.get("setup") or "").strip(),
                rules=(parsed.get("rules") or "").strip(),
            )
            missing = [field for field in FIELDS if not getattr(result, field)]
            return result, missing, None
        except Exception:
            return None, [], "Brain dump failed, please enter fields manually."


_splitter: BrainDumpSplitter | None = None


def get_brain_dump_splitter() -> BrainDumpSplitter:
    global _splitter
    if _splitter is None:
        _splitter = BrainDumpSplitter()
    return _splitter
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/utils/prompts.py src/services/brain_dump.py tests/api/optimise/test_brain_dump_service.py
git commit -m "$(cat <<'EOF'
feat(brain-dump): add splitter service and prompt

One gpt-4.1-mini call with JSON-schema structured output splits a
freeform dump into objective/setup/rules, reports empty fields as
missing, and falls back to an error on any OpenAI/parse failure.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed
EOF
)"
```

---

## Task 3: Endpoint

**Files:**
- Modify: `src/api/optimisation.py`
- Test: `tests/api/optimise/test_brain_dump.py` (extend the file from Task 1)

**Interfaces:**
- Consumes: `BrainDumpRequest`, `BrainDumpResponse` (Task 1); `get_brain_dump_splitter`, `MIN_DUMP_LENGTH` (Task 2); existing `check_content`, `auth_required`, `User`.
- Produces: `POST /optimise/brain-dump` returning `BrainDumpResponse`; module constant `MAX_DUMP_LENGTH = 4000`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/optimise/test_brain_dump.py`:

```python
from unittest.mock import MagicMock, patch

from src.models.optimisation_models.brain_dump_models import BrainDumpResult


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump.py -v`
Expected: FAIL — the new endpoint route returns 404 (route not defined) / import errors for `get_brain_dump_splitter` patch target.

- [ ] **Step 3: Add the endpoint**

Modify `src/api/optimisation.py`. Add imports near the existing imports:

```python
from src.models.optimisation_models.brain_dump_models import BrainDumpRequest, BrainDumpResponse
from src.services.brain_dump import get_brain_dump_splitter, MIN_DUMP_LENGTH
```

Add a module constant after `router = APIRouter()`:

```python
MAX_DUMP_LENGTH = 4000
```

Add the route (after the existing `optimise_text` handler):

```python
@router.post("/brain-dump", response_model=BrainDumpResponse)
async def brain_dump(request: BrainDumpRequest, _current_user: User = auth_required()):
    dump = request.dump_text.strip()

    if len(dump) < MIN_DUMP_LENGTH:
        return BrainDumpResponse(
            success=False,
            data=None,
            missing_fields=[],
            error_message="Text too short to split.",
        )

    if len(dump) > MAX_DUMP_LENGTH:
        raise HTTPException(status_code=422, detail="Brain dump text is too long (max 4000 characters).")

    if not check_content(dump):
        raise HTTPException(status_code=422, detail="Content violates community guidelines.")

    result, missing, error = get_brain_dump_splitter().split(dump)

    if result is None:
        return BrainDumpResponse(
            success=False, data=None, missing_fields=[], error_message=error
        )

    return BrainDumpResponse(
        success=True, data=result, missing_fields=missing, error_message=None
    )
```

Note: `BrainDumpRequest.dump_text` has `max_length=4000`, so an over-length body is rejected as a `422` validation error by FastAPI before the handler runs. The explicit in-handler `MAX_DUMP_LENGTH` check is a belt-and-braces guard for callers constructing the model directly; both paths return `422`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/test_brain_dump.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Run the full optimise + games suites for regressions**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/optimise/ tests/api/games/ -q`
Expected: PASS (no regressions)

- [ ] **Step 6: Update the knowledge graph**

Run: `graphify update .`

- [ ] **Step 7: Commit**

```bash
git add src/api/optimisation.py tests/api/optimise/test_brain_dump.py
git commit -m "$(cat <<'EOF'
feat(brain-dump): add POST /optimise/brain-dump endpoint

Validates length and moderation, delegates to the splitter service,
and returns a non-persisted draft with missing_fields for the frontend.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Endpoint `POST /optimise/brain-dump`, auth required → Task 3. ✓
- Request/response shape incl. `missing_fields` → Task 1 models, Task 3 wiring. ✓
- `gpt-4.1-mini` + JSON-schema structured output, temp 0.2 → Task 2 service. ✓
- 3 fields only, empty-on-absent, never invent → Task 2 prompt + schema. ✓
- Guardrails: min length (success=false), max length (422), moderation (422), upstream failure (success=false) → Task 2 (failure) + Task 3 (length/moderation). ✓
- Non-persisted → no game writes anywhere. ✓
- Frontend contract → documented in the spec; no backend task needed. ✓
- Testing: happy, partial, too-short (no OpenAI call), moderation, max-length, upstream-fail, auth → Task 2 + Task 3 tests. ✓
- Cost / no-agent decision → design-only, no code. ✓

**Placeholder scan:** none — all steps carry real code and exact commands.

**Type consistency:** `split()` returns `(BrainDumpResult | None, list[str], str | None)` in Task 2 and is consumed with that exact unpacking in Task 3. `get_brain_dump_splitter` / `MIN_DUMP_LENGTH` names match across service and endpoint. `BrainDumpResponse` fields match across Task 1 definition and Task 3 construction.
