from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.users import get_current_user_optional
from src.db.database import get_db
from src.db.tables import PushToken
from src.main import app


# Registration takes optional auth, so these tests must override get_current_user_optional —
# the shared client_with_auth fixture only overrides get_current_active_user, which this
# router no longer uses. Overriding the wrong dependency makes an "authenticated" client
# silently anonymous and the ownership assertions pass vacuously.
@pytest.fixture
def client_as_user(db, test_user):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = lambda: test_user

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestRegisterPushToken:
    def test_creates_new_token(self, client_as_user, db, test_user):
        response = client_as_user.post(
            "/push-tokens/", json={"token": "ExponentPushToken[a]", "platform": "ios"}
        )
        assert response.status_code == 201

        row = db.query(PushToken).filter_by(token="ExponentPushToken[a]").first()
        assert row.user_id == test_user.id
        assert row.platform == "ios"

    def test_rejects_malformed_token(self, client_as_user, db):
        response = client_as_user.post(
            "/push-tokens/", json={"token": "some-old-fcm-token-not-expo-format", "platform": "ios"}
        )
        assert response.status_code == 400
        assert db.query(PushToken).filter_by(token="some-old-fcm-token-not-expo-format").first() is None

    def test_upserts_existing_token_to_new_owner(self, client_as_user, db, second_user, test_user):
        # Seed the token as owned by second_user directly in the DB — do NOT use a second
        # client fixture here. app.dependency_overrides is one dict on one app object; using
        # two client fixtures (e.g. client_as_user + client_as_second_user) in the same test
        # means the second one's override wins for the whole test body, silently collapsing
        # both "clients" onto the same user and making this test pass vacuously.
        db.add(PushToken(token="ExponentPushToken[shared]", user_id=second_user.id, platform="android"))
        db.commit()

        response = client_as_user.post(
            "/push-tokens/", json={"token": "ExponentPushToken[shared]", "platform": "ios"}
        )
        assert response.status_code == 200

        rows = db.query(PushToken).filter_by(token="ExponentPushToken[shared]").all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].platform == "ios"

    def test_reregistering_unchanged_token_bumps_updated_at(self, client_as_user, db, test_user):
        # The app re-registers on every launch with the same user_id and platform. Without an
        # explicit stamp SQLAlchemy sees no net change, emits no UPDATE, and updated_at stays
        # at first registration — which is what made stale tokens indistinguishable from live
        # ones in prod.
        stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=45)
        db.add(PushToken(
            token="ExponentPushToken[same]", user_id=test_user.id, platform="ios", updated_at=stale,
        ))
        db.commit()

        response = client_as_user.post(
            "/push-tokens/", json={"token": "ExponentPushToken[same]", "platform": "ios"}
        )
        assert response.status_code == 200

        row = db.query(PushToken).filter_by(token="ExponentPushToken[same]").first()
        assert row.updated_at > stale

    def test_stores_device_id_when_sent(self, client_as_user, db):
        response = client_as_user.post(
            "/push-tokens/",
            json={"token": "ExponentPushToken[d]", "platform": "ios", "device_id": "device-1"},
        )
        assert response.status_code == 201
        assert db.query(PushToken).filter_by(token="ExponentPushToken[d]").first().device_id == "device-1"


class TestRegisterWithoutAuth:
    def test_creates_unclaimed_row(self, client_no_auth, db):
        # The tutorial-completion path fires registration with no session. This used to 401
        # and leave the device with OS-level notifications on and no row here.
        response = client_no_auth.post(
            "/push-tokens/",
            json={"token": "ExponentPushToken[anon]", "platform": "ios", "device_id": "device-9"},
        )
        assert response.status_code == 201

        row = db.query(PushToken).filter_by(token="ExponentPushToken[anon]").first()
        assert row.user_id is None
        assert row.device_id == "device-9"

    def test_works_without_device_id_for_old_builds(self, client_no_auth, db):
        response = client_no_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[old]", "platform": "android"}
        )
        assert response.status_code == 201

        row = db.query(PushToken).filter_by(token="ExponentPushToken[old]").first()
        assert row.user_id is None
        assert row.device_id is None

    def test_does_not_strip_owner_from_a_claimed_token(self, client_no_auth, db, test_user):
        # A request that lost its auth (expired token, failed refresh) must not downgrade an
        # already-claimed device to broadcast-only.
        db.add(PushToken(token="ExponentPushToken[mine]", user_id=test_user.id, platform="ios"))
        db.commit()

        response = client_no_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[mine]", "platform": "ios"}
        )
        assert response.status_code == 200
        assert db.query(PushToken).filter_by(token="ExponentPushToken[mine]").first().user_id == test_user.id


class TestClaimOnSignIn:
    def test_authenticated_register_claims_the_anonymous_row(self, client_as_user, db, test_user):
        db.add(PushToken(
            token="ExponentPushToken[anon]", user_id=None, device_id="device-7", platform="ios",
        ))
        db.commit()

        response = client_as_user.post(
            "/push-tokens/",
            json={"token": "ExponentPushToken[anon]", "platform": "ios", "device_id": "device-7"},
        )
        assert response.status_code == 200

        rows = db.query(PushToken).filter_by(device_id="device-7").all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id

    def test_rotated_token_leaves_one_row_per_device(self, client_as_user, db, test_user):
        # Expo rotated the token for this install. Without the device_id sweep the old
        # anonymous row survives and audience="all" delivers to the device twice.
        db.add(PushToken(
            token="ExponentPushToken[old]", user_id=None, device_id="device-7", platform="ios",
        ))
        db.commit()

        response = client_as_user.post(
            "/push-tokens/",
            json={"token": "ExponentPushToken[new]", "platform": "ios", "device_id": "device-7"},
        )
        assert response.status_code == 201

        rows = db.query(PushToken).filter_by(device_id="device-7").all()
        assert len(rows) == 1
        assert rows[0].token == "ExponentPushToken[new]"
        assert rows[0].user_id == test_user.id

    def test_other_devices_of_the_same_user_are_untouched(self, client_as_user, db, test_user):
        db.add(PushToken(
            token="ExponentPushToken[phone]", user_id=test_user.id, device_id="device-1", platform="ios",
        ))
        db.commit()

        client_as_user.post(
            "/push-tokens/",
            json={"token": "ExponentPushToken[tablet]", "platform": "ios", "device_id": "device-2"},
        )

        assert db.query(PushToken).filter_by(user_id=test_user.id).count() == 2


class TestDeletePushToken:
    def test_deletes_own_token(self, client_as_user, db, test_user):
        db.add(PushToken(token="ExponentPushToken[mine]", user_id=test_user.id, platform="ios"))
        db.commit()

        response = client_as_user.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[mine]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[mine]").first() is None

    def test_does_not_delete_other_users_token(self, client_as_user, db, second_user):
        db.add(PushToken(token="ExponentPushToken[theirs]", user_id=second_user.id, platform="ios"))
        db.commit()

        response = client_as_user.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[theirs]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[theirs]").first() is not None

    def test_nonexistent_token_still_204(self, client_as_user):
        response = client_as_user.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[nope]"})
        assert response.status_code == 204

    def test_signed_out_device_can_unsubscribe_itself(self, client_no_auth, db):
        db.add(PushToken(token="ExponentPushToken[anon]", user_id=None, platform="ios"))
        db.commit()

        response = client_no_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[anon]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[anon]").first() is None

    def test_signed_out_caller_cannot_delete_a_claimed_token(self, client_no_auth, db, test_user):
        db.add(PushToken(token="ExponentPushToken[mine]", user_id=test_user.id, platform="ios"))
        db.commit()

        response = client_no_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[mine]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[mine]").first() is not None


class TestDeleteByDeviceId:
    def test_revoked_device_can_unsubscribe_without_its_token(self, client_as_user, db, test_user):
        # A device whose notifications were revoked in OS settings cannot fetch its Expo token
        # any more (getExpoPushTokenAsync throws without permission), so device_id is the only
        # identifier it still holds. Without this path the row survives and the device keeps
        # counting as reachable while the OS silently drops every send.
        db.add(PushToken(
            token="ExponentPushToken[revoked]", user_id=test_user.id, device_id="d1", platform="ios",
        ))
        db.commit()

        response = client_as_user.request("DELETE", "/push-tokens/", json={"device_id": "d1"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(device_id="d1").first() is None

    def test_signed_out_revoked_device_can_unsubscribe(self, client_no_auth, db):
        db.add(PushToken(token="ExponentPushToken[anon]", user_id=None, device_id="d2", platform="ios"))
        db.commit()

        response = client_no_auth.request("DELETE", "/push-tokens/", json={"device_id": "d2"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(device_id="d2").first() is None

    def test_does_not_delete_another_users_device_row(self, client_as_user, db, second_user):
        db.add(PushToken(
            token="ExponentPushToken[theirs]", user_id=second_user.id, device_id="d3", platform="ios",
        ))
        db.commit()

        response = client_as_user.request("DELETE", "/push-tokens/", json={"device_id": "d3"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(device_id="d3").first() is not None

    def test_both_identifiers_clears_the_row_after_token_rotation(self, client_as_user, db, test_user):
        # The app sends the token it believes it has plus its device_id. If Expo rotated the
        # token since registration, only device_id still matches — OR-ing them still clears it.
        db.add(PushToken(
            token="ExponentPushToken[old]", user_id=test_user.id, device_id="d4", platform="ios",
        ))
        db.commit()

        response = client_as_user.request(
            "DELETE", "/push-tokens/",
            json={"token": "ExponentPushToken[rotated]", "device_id": "d4"},
        )
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(device_id="d4").first() is None

    def test_empty_body_is_422(self, client_as_user):
        response = client_as_user.request("DELETE", "/push-tokens/", json={})
        assert response.status_code == 422
