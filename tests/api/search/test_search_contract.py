"""
Characterisation tests for POST /games/search/.

These pin the behaviour the endpoint has *today* so it can be refactored
safely: the plan is to stop loading the whole catalogue with joinedloads to
return a handful of rows, and to score with one vectorised matmul instead of
135 separate cosine calls. Neither should change a single result.

Written before that refactor and verified green against the current
implementation, so a later failure means the refactor moved behaviour rather
than these tests describing an intent that was never true.

Existing coverage in test_search.py handles equipment negation and player
count. This file covers what that leaves: ranking order, score values, limit,
and the visibility filters (private / unapproved / embedding-less / adult).
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.users import get_current_active_user, get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, User
from src.main import app

_SEARCH_PATCH_TARGET = "src.api.search.embed_query"

DIMS = 1536


def _vec(*leading: float) -> list[float]:
    """A unit-ish vector with the given leading components, zero elsewhere."""
    return list(leading) + [0.0] * (DIMS - len(leading))


QUERY_VECTOR = _vec(1.0)
EXACT_MATCH = _vec(1.0)          # cosine 1.0 against the query
PARTIAL_MATCH = _vec(0.6, 0.8)   # unit length, cosine 0.6
ORTHOGONAL = _vec(0.0, 1.0)      # cosine 0.0


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _make_user(db, age_years: int) -> User:
    return _add(
        db,
        User(
            id=str(uuid.uuid4()),
            firstname="Test",
            lastname="User",
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            date_of_birth=(date.today() - timedelta(days=365 * age_years)).isoformat(),
            country_of_origin="GB",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ),
    )


def _add(db, obj):
    db.add(obj)
    db.flush()
    return obj


def _make_game(
    db,
    contributor,
    embedding,
    *,
    name=None,
    is_public=True,
    status="approved",
    has_adult_content=False,
    min_players=2,
    max_players=6,
    equipment="No Equipment",
):
    game = _add(
        db,
        Game(
            id=str(uuid.uuid4()),
            name=name or f"Game {uuid.uuid4().hex[:6]}",
            description="A test game",
            game_type="Card",
            min_players=min_players,
            max_players=max_players,
            duration="30-45 mins",
            objective="Win",
            setup="Set up",
            rules="Play",
            is_public=is_public,
            status=status,
            is_whats_that_game_verified=False,
            has_adult_content=has_adult_content,
            upvotes=0,
            embedding=json.dumps(embedding) if embedding is not None else None,
            contributor_id=contributor.id,
            created_at=datetime.now(timezone.utc),
        ),
    )
    db.add(GameEquipment(game_id=game.id, equipment_name=equipment))
    db.commit()
    return game


def _client_as(db, user):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def _search(client, query="find me a game", limit=20, player_count=None):
    body = {"query": query, "limit": limit}
    if player_count is not None:
        body["player_count"] = player_count
    with patch(_SEARCH_PATCH_TARGET, return_value=QUERY_VECTOR):
        response = client.post("/games/search/", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# Ranking - the thing the vectorised-scoring change could break
# --------------------------------------------------------------------------

def test_results_are_ordered_by_descending_similarity(db):
    user = _make_user(db, 30)
    far = _make_game(db, user, ORTHOGONAL, name="Far Game")
    near = _make_game(db, user, EXACT_MATCH, name="Near Game")
    middle = _make_game(db, user, PARTIAL_MATCH, name="Middle Game")

    results = _search(_client_as(db, user))

    returned = [r["id"] for r in results]
    assert returned.index(near.id) < returned.index(middle.id) < returned.index(far.id)


def test_scores_reflect_cosine_similarity(db):
    user = _make_user(db, 30)
    _make_game(db, user, EXACT_MATCH, name="Exact")
    _make_game(db, user, PARTIAL_MATCH, name="Partial")

    by_name = {r["name"]: r["score"] for r in _search(_client_as(db, user))}

    assert by_name["Exact"] == pytest.approx(1.0, abs=1e-3)
    assert by_name["Partial"] == pytest.approx(0.6, abs=1e-3)


def test_limit_caps_the_number_of_results(db):
    user = _make_user(db, 30)
    for _ in range(5):
        _make_game(db, user, EXACT_MATCH)

    assert len(_search(_client_as(db, user), limit=2)) == 2


def test_limit_returns_the_highest_scoring_games(db):
    user = _make_user(db, 30)
    _make_game(db, user, ORTHOGONAL, name="Worst")
    best = _make_game(db, user, EXACT_MATCH, name="Best")

    results = _search(_client_as(db, user), limit=1)

    assert [r["id"] for r in results] == [best.id]


# --------------------------------------------------------------------------
# Visibility filters - these move from Python into SQL in the refactor
# --------------------------------------------------------------------------

def test_private_games_are_excluded(db):
    user = _make_user(db, 30)
    private = _make_game(db, user, EXACT_MATCH, is_public=False)

    assert private.id not in [r["id"] for r in _search(_client_as(db, user))]


def test_unapproved_games_are_excluded(db):
    user = _make_user(db, 30)
    pending = _make_game(db, user, EXACT_MATCH, status="pending")

    assert pending.id not in [r["id"] for r in _search(_client_as(db, user))]


def test_games_without_an_embedding_are_excluded(db):
    user = _make_user(db, 30)
    unembedded = _make_game(db, user, None)

    assert unembedded.id not in [r["id"] for r in _search(_client_as(db, user))]


def test_adult_games_hidden_from_minors_and_shown_to_adults(db):
    adult = _make_user(db, 30)
    minor = _make_user(db, 15)
    spicy = _make_game(db, adult, EXACT_MATCH, has_adult_content=True)

    assert spicy.id not in [r["id"] for r in _search(_client_as(db, minor))]
    assert spicy.id in [r["id"] for r in _search(_client_as(db, adult))]


# --------------------------------------------------------------------------
# Filter interaction - ranking must not leak past a hard filter
# --------------------------------------------------------------------------

def test_player_count_filter_applies_before_ranking(db):
    """
    The best-scoring game is out of player range, so it must be dropped and
    the weaker in-range game returned - not dropped from the top slice after
    ranking, which would return nothing.
    """
    user = _make_user(db, 30)
    _make_game(db, user, EXACT_MATCH, name="Too Big", min_players=8, max_players=10)
    in_range = _make_game(db, user, PARTIAL_MATCH, name="Fits", min_players=2, max_players=4)

    results = _search(_client_as(db, user), limit=1, player_count=3)

    assert [r["id"] for r in results] == [in_range.id]
