import uuid
from datetime import datetime, timedelta, timezone

from src.db.tables import Notification, ScheduledNotification

DRAFT = {"title": "New games this week", "body": "Come and have a look", "send_at": "2026-11-02T17:00:00"}


def create(client, *drafts):
    response = client.post("/admin/notifications/scheduled", json={"drafts": list(drafts) or [DRAFT]})
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateDrafts:
    def test_requires_admin(self, client_with_auth):
        response = client_with_auth.post("/admin/notifications/scheduled", json={"drafts": [DRAFT]})
        assert response.status_code == 403

    def test_batch_shares_one_batch_id_and_starts_as_draft(self, client_as_admin, db):
        out = create(client_as_admin, DRAFT, {**DRAFT, "title": "Second", "source": "claude", "rationale": "trending"})

        rows = db.query(ScheduledNotification).filter(ScheduledNotification.batch_id == out["batch_id"]).all()
        assert len(rows) == 2 and set(out["ids"]) == {r.id for r in rows}
        assert {r.status for r in rows} == {"draft"}
        assert {r.source for r in rows} == {"admin", "claude"}
        assert all(r.local_time for r in rows)  # wall-clock in each device's zone by default

    def test_game_id_is_stored_as_deep_link_data(self, client_as_admin, db):
        out = create(client_as_admin, {**DRAFT, "game_id": "g-1"})
        assert db.get(ScheduledNotification, out["ids"][0]).data == '{"game_id": "g-1"}'

    def test_aware_send_at_is_converted_to_naive_utc(self, client_as_admin, db):
        out = create(client_as_admin, {**DRAFT, "send_at": "2026-11-02T17:00:00+01:00"})
        assert db.get(ScheduledNotification, out["ids"][0]).send_at == datetime(2026, 11, 2, 16, 0)

    def test_push_length_limits_are_enforced(self, client_as_admin):
        too_long = client_as_admin.post(
            "/admin/notifications/scheduled", json={"drafts": [{**DRAFT, "body": "x" * 200}]}
        )
        empty = client_as_admin.post("/admin/notifications/scheduled", json={"drafts": []})
        assert too_long.status_code == 422 and empty.status_code == 422


class TestListAndCalendar:
    def test_default_lists_only_what_is_still_to_go_out_soonest_first(self, client_as_admin):
        later = create(client_as_admin, {**DRAFT, "send_at": "2026-11-09T17:00:00"})["ids"][0]
        sooner = create(client_as_admin, DRAFT)["ids"][0]
        cancelled = create(client_as_admin, {**DRAFT, "title": "Nope"})["ids"][0]
        client_as_admin.patch(f"/admin/notifications/scheduled/{cancelled}", json={"status": "cancelled"})

        listed = client_as_admin.get("/admin/notifications/scheduled").json()
        assert [r["id"] for r in listed if r["id"] in (later, sooner, cancelled)] == [sooner, later]

    def test_filters_by_status_and_batch(self, client_as_admin):
        a = create(client_as_admin)
        b = create(client_as_admin)
        client_as_admin.post(f"/admin/notifications/scheduled/batches/{a['batch_id']}/approve")

        approved = client_as_admin.get("/admin/notifications/scheduled?status=approved").json()
        assert {r["id"] for r in approved} >= set(a["ids"]) and not set(b["ids"]) & {r["id"] for r in approved}
        only_b = client_as_admin.get(f"/admin/notifications/scheduled?batch_id={b['batch_id']}").json()
        assert [r["id"] for r in only_b] == b["ids"]

    def test_requires_admin(self, client_with_auth):
        assert client_with_auth.get("/admin/notifications/scheduled").status_code == 403


class TestBatchApproval:
    def test_approves_every_draft_in_one_call_and_records_who(self, client_as_admin, db, admin_user):
        out = create(client_as_admin, DRAFT, {**DRAFT, "title": "Two"}, {**DRAFT, "title": "Three"})

        response = client_as_admin.post(f"/admin/notifications/scheduled/batches/{out['batch_id']}/approve")
        assert response.status_code == 200
        assert response.json() == {"batch_id": out["batch_id"], "approved": 3}

        rows = db.query(ScheduledNotification).filter_by(batch_id=out["batch_id"]).all()
        assert {r.status for r in rows} == {"approved"}
        assert {r.approved_by for r in rows} == {admin_user.id}
        assert all(r.approved_at for r in rows)

    def test_cancelled_rows_stay_cancelled(self, client_as_admin, db):
        out = create(client_as_admin, DRAFT, {**DRAFT, "title": "Drop me"})
        client_as_admin.patch(f"/admin/notifications/scheduled/{out['ids'][1]}", json={"status": "cancelled"})

        response = client_as_admin.post(f"/admin/notifications/scheduled/batches/{out['batch_id']}/approve")
        assert response.json()["approved"] == 1
        assert db.get(ScheduledNotification, out["ids"][1]).status == "cancelled"

    def test_is_idempotent(self, client_as_admin):
        out = create(client_as_admin)
        url = f"/admin/notifications/scheduled/batches/{out['batch_id']}/approve"
        client_as_admin.post(url)
        assert client_as_admin.post(url).json()["approved"] == 0

    def test_unknown_batch_is_404(self, client_as_admin):
        assert client_as_admin.post(f"/admin/notifications/scheduled/batches/{uuid.uuid4()}/approve").status_code == 404

    def test_requires_admin(self, client_with_auth):
        assert client_with_auth.post("/admin/notifications/scheduled/batches/x/approve").status_code == 403


class TestPatch:
    def test_approve_single_row(self, client_as_admin):
        row_id = create(client_as_admin)["ids"][0]
        response = client_as_admin.patch(f"/admin/notifications/scheduled/{row_id}", json={"status": "approved"})
        assert response.status_code == 200 and response.json()["status"] == "approved"

    def test_editing_approved_copy_sends_it_back_to_draft(self, client_as_admin, db):
        row_id = create(client_as_admin)["ids"][0]
        client_as_admin.patch(f"/admin/notifications/scheduled/{row_id}", json={"status": "approved"})

        response = client_as_admin.patch(f"/admin/notifications/scheduled/{row_id}", json={"body": "Changed copy"})
        assert response.json()["status"] == "draft"
        assert response.json()["body"] == "Changed copy"
        assert db.get(ScheduledNotification, row_id).approved_at is None

    def test_edit_and_approve_in_one_request_stays_approved(self, client_as_admin):
        row_id = create(client_as_admin)["ids"][0]
        response = client_as_admin.patch(
            f"/admin/notifications/scheduled/{row_id}", json={"title": "Better title", "status": "approved"}
        )
        assert response.json()["status"] == "approved" and response.json()["title"] == "Better title"

    def test_sent_row_cannot_be_changed(self, client_as_admin, db):
        row_id = create(client_as_admin)["ids"][0]
        db.get(ScheduledNotification, row_id).status = "sent"
        db.flush()
        response = client_as_admin.patch(f"/admin/notifications/scheduled/{row_id}", json={"status": "cancelled"})
        assert response.status_code == 409

    def test_unknown_row_is_404(self, client_as_admin):
        assert client_as_admin.patch(f"/admin/notifications/scheduled/{uuid.uuid4()}", json={"status": "approved"}).status_code == 404


class TestCampaignsAndStats:
    def test_lists_the_fixed_lifecycle_campaigns(self, client_as_admin):
        campaigns = client_as_admin.get("/admin/notifications/campaigns").json()
        assert [c["key"] for c in campaigns][0] == "lifecycle_day_2_no_submit"
        assert all({"key", "day", "title", "body"} == set(c) for c in campaigns)

    def test_stats_count_outcomes_and_open_rate_per_type(self, client_as_admin, db, test_user):
        now = datetime.now(timezone.utc)

        def note(status, opened=False, type="lifecycle_day_2_no_submit", age_days=1):
            db.add(Notification(
                id=str(uuid.uuid4()), user_id=test_user.id, type=type, title="t", body="b", status=status,
                created_at=now - timedelta(days=age_days), opened_at=now if opened else None,
            ))

        note("sent", opened=True)
        note("sent")
        note("failed")
        note("no_token")
        note("sent", age_days=60)  # outside the default 30-day window
        db.flush()

        stats = {s["type"]: s for s in client_as_admin.get("/admin/notifications/stats").json()}
        s = stats["lifecycle_day_2_no_submit"]
        assert (s["total"], s["sent"], s["failed"], s["no_token"], s["opened"]) == (4, 2, 1, 1, 1)
        assert s["open_rate"] == 0.5

    def test_stats_requires_admin(self, client_with_auth):
        assert client_with_auth.get("/admin/notifications/stats").status_code == 403


class TestTimezoneHealth:
    @staticmethod
    def add(db, n, zone=None, error=None, prefix="t"):
        from src.db.tables import PushToken
        for i in range(n):
            db.add(PushToken(token=f"ExponentPushToken[{prefix}{zone}{error}{i}]", platform="ios",
                             timezone=zone, timezone_error=error))
        db.commit()

    def test_requires_admin(self, client_with_auth):
        assert client_with_auth.get("/admin/notifications/timezones").status_code == 403

    def test_buckets_and_no_warning_when_healthy(self, client_as_admin, db):
        self.add(db, 3, zone="Europe/London")
        self.add(db, 1, zone="UTC")
        self.add(db, 2)  # old builds
        out = client_as_admin.get("/admin/notifications/timezones").json()

        assert (out["reported"], out["not_reported"], out["invalid"], out["utc"]) == (4, 2, 0, 1)
        assert out["utc_share"] == 0.25
        assert out["top_zones"][0] == {"value": "Europe/London", "count": 3}
        assert out["warning"] is None

    def test_warns_when_most_reporting_devices_say_utc(self, client_as_admin, db):
        self.add(db, 25, zone="UTC")
        self.add(db, 2, zone="Europe/London")
        out = client_as_admin.get("/admin/notifications/timezones").json()
        assert "UTC" in out["warning"]

    def test_small_samples_do_not_trigger_the_utc_warning(self, client_as_admin, db):
        self.add(db, 3, zone="UTC")
        assert client_as_admin.get("/admin/notifications/timezones").json()["warning"] is None

    def test_invalid_names_are_counted_and_sampled(self, client_as_admin, db):
        self.add(db, 2, error="Mars/Olympus")
        out = client_as_admin.get("/admin/notifications/timezones").json()
        assert out["invalid"] == 2 and out["not_reported"] == 0
        assert out["invalid_samples"] == [{"value": "Mars/Olympus", "count": 2}]
        assert "not an IANA zone" in out["warning"]
