import pytest
from tests.api.games.helper import create_public_game
from tests.conftest import client_with_auth, client_no_auth


def test_suggest_alias_returns_201(client_with_auth):
    game = create_public_game(client_with_auth)
    response = client_with_auth.post(
        f"/games/{game['id']}/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["alias"] == "BS"
    assert data["status"] == "pending"
    assert data["game_id"] == game["id"]


def test_suggest_alias_unauthenticated_returns_401(client_no_auth):
    response = client_no_auth.post(
        "/games/some-game-id/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 401


def test_suggest_alias_unknown_game_returns_404(client_with_auth):
    response = client_with_auth.post(
        "/games/nonexistent-id/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 404


def test_get_aliases_returns_only_approved(client_with_auth, db):
    from src.db.tables import GameAlias
    game = create_public_game(client_with_auth)

    # Suggest two aliases
    client_with_auth.post(f"/games/{game['id']}/aliases", json={"alias": "BS"})
    client_with_auth.post(f"/games/{game['id']}/aliases", json={"alias": "Cheat"})

    # Manually approve one in DB
    alias = db.query(GameAlias).filter(GameAlias.alias == "BS").first()
    alias.status = "approved"
    db.commit()

    response = client_with_auth.get(f"/games/{game['id']}/aliases")
    assert response.status_code == 200
    names = [a["alias"] for a in response.json()]
    assert "BS" in names
    assert "Cheat" not in names


def test_get_aliases_unknown_game_returns_404(client_no_auth):
    response = client_no_auth.get("/games/nonexistent-id/aliases")
    assert response.status_code == 404
