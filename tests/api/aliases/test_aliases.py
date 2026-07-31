import pytest
from tests.api.games.helper import create_public_game
from tests.conftest import client_with_auth, client_no_auth, client_as_admin


def test_suggest_alias_returns_201(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = client_with_auth.post(
        f"/games/{game['id']}/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["alias"] == "BS"
    assert data["status"] == "pending"
    assert data["game_id"] == game["id"]


def test_suggest_alias_unauthenticated_returns_401(client_no_auth, db):
    response = client_no_auth.post(
        "/games/some-game-id/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 401


def test_suggest_alias_unknown_game_returns_404(client_with_auth, db):
    response = client_with_auth.post(
        "/games/nonexistent-id/aliases",
        json={"alias": "BS"},
    )
    assert response.status_code == 404


def test_get_aliases_returns_only_approved(client_with_auth, db):
    from src.db.tables import GameAlias
    game = create_public_game(client_with_auth, db)

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


def test_get_aliases_unknown_game_returns_404(client_no_auth, db):
    response = client_no_auth.get("/games/nonexistent-id/aliases")
    assert response.status_code == 404


def test_admin_can_list_pending_aliases(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    client_with_auth.post(f"/games/{game['id']}/aliases", json={"alias": "BS"})

    response = client_as_admin.get("/admin/aliases")
    assert response.status_code == 200
    aliases_list = response.json()
    assert any(a["alias"] == "BS" for a in aliases_list)


def test_non_admin_cannot_list_aliases(client_with_auth, db):
    response = client_with_auth.get("/admin/aliases")
    assert response.status_code == 403


def test_admin_can_approve_alias(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "BS"}
    )
    alias_id = suggest.json()["id"]

    response = client_as_admin.patch(
        f"/admin/aliases/{alias_id}", json={"status": "approved"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_admin_can_reject_alias(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "BS"}
    )
    alias_id = suggest.json()["id"]

    response = client_as_admin.patch(
        f"/admin/aliases/{alias_id}", json={"status": "rejected"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_non_admin_cannot_patch_alias(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "BS"}
    )
    alias_id = suggest.json()["id"]

    response = client_with_auth.patch(
        f"/admin/aliases/{alias_id}", json={"status": "approved"}
    )
    assert response.status_code == 403


def test_alias_patch_invalid_status_returns_422(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "BS"}
    )
    alias_id = suggest.json()["id"]

    response = client_as_admin.patch(
        f"/admin/aliases/{alias_id}", json={"status": "invalid"}
    )
    assert response.status_code == 422


def test_approved_alias_appears_in_game_response(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "BS"}
    )
    alias_id = suggest.json()["id"]
    client_as_admin.patch(f"/admin/aliases/{alias_id}", json={"status": "approved"})

    response = client_with_auth.get(f"/games/{game['id']}")
    assert "BS" in response.json()["aliases"]


def test_name_filter_matches_approved_alias(client_with_auth, client_as_admin, db):
    game = create_public_game(client_with_auth, db)
    suggest = client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "UniqueAliasXYZ"}
    )
    alias_id = suggest.json()["id"]
    client_as_admin.patch(f"/admin/aliases/{alias_id}", json={"status": "approved"})

    response = client_with_auth.get("/games/?name=UniqueAliasXYZ")
    assert response.status_code == 200
    ids = [g["id"] for g in response.json()]
    assert game["id"] in ids


def test_name_filter_does_not_match_pending_alias(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    client_with_auth.post(
        f"/games/{game['id']}/aliases", json={"alias": "PendingAliasABC"}
    )

    response = client_with_auth.get("/games/?name=PendingAliasABC")
    ids = [g["id"] for g in response.json()]
    assert game["id"] not in ids
