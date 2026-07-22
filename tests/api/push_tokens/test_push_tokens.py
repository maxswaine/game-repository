from src.db.tables import PushToken


class TestRegisterPushToken:
    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[a]", "platform": "ios"}
        )
        assert response.status_code == 401

    def test_creates_new_token(self, client_with_auth, db, test_user):
        response = client_with_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[a]", "platform": "ios"}
        )
        assert response.status_code == 201

        row = db.query(PushToken).filter_by(token="ExponentPushToken[a]").first()
        assert row.user_id == test_user.id
        assert row.platform == "ios"

    def test_rejects_malformed_token(self, client_with_auth, db):
        response = client_with_auth.post(
            "/push-tokens/", json={"token": "some-old-fcm-token-not-expo-format", "platform": "ios"}
        )
        assert response.status_code == 400
        assert db.query(PushToken).filter_by(token="some-old-fcm-token-not-expo-format").first() is None

    def test_upserts_existing_token_to_new_owner(self, client_with_auth, db, second_user, test_user):
        # Seed the token as owned by second_user directly in the DB — do NOT use a second
        # client fixture here. app.dependency_overrides is one dict on one app object; using
        # two client fixtures (e.g. client_with_auth + client_as_second_user) in the same test
        # means the second one's override wins for the whole test body, silently collapsing
        # both "clients" onto the same user and making this test pass vacuously.
        db.add(PushToken(token="ExponentPushToken[shared]", user_id=second_user.id, platform="android"))
        db.commit()

        response = client_with_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[shared]", "platform": "ios"}
        )
        assert response.status_code == 200

        rows = db.query(PushToken).filter_by(token="ExponentPushToken[shared]").all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].platform == "ios"


class TestDeletePushToken:
    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.request("DELETE", "/push-tokens/", json={"token": "x"})
        assert response.status_code == 401

    def test_deletes_own_token(self, client_with_auth, db, test_user):
        db.add(PushToken(token="ExponentPushToken[mine]", user_id=test_user.id, platform="ios"))
        db.commit()

        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[mine]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[mine]").first() is None

    def test_does_not_delete_other_users_token(self, client_with_auth, db, second_user):
        db.add(PushToken(token="ExponentPushToken[theirs]", user_id=second_user.id, platform="ios"))
        db.commit()

        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[theirs]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[theirs]").first() is not None

    def test_nonexistent_token_still_204(self, client_with_auth):
        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[nope]"})
        assert response.status_code == 204
