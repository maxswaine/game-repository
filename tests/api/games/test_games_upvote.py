from tests.api.games.helper import create_public_game, upvote_game


class TestUpvoteToggleResponse:
    def test_upvote_returns_liked_by_me_true(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)

        response = upvote_game(client_with_auth, game["id"])

        assert response.status_code == 200
        body = response.json()
        assert body["game_id"] == game["id"]
        assert body["upvotes"] == 1
        assert body["liked_by_me"] is True

    def test_second_upvote_toggles_liked_by_me_false(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)

        upvote_game(client_with_auth, game["id"])  # like
        response = upvote_game(client_with_auth, game["id"])  # unlike

        assert response.status_code == 200
        body = response.json()
        assert body["upvotes"] == 0
        assert body["liked_by_me"] is False
