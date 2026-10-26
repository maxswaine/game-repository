import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.db.tables import Game, Notification, PushToken, ScheduledNotification, User, UserFavourites
from src.services import notification_automation as auto
from src.utils import config

UTC = timezone.utc
# Monday 2026-10-26 17:00 UTC. London is back on GMT (clocks changed on the 25th) so it is also
# 17:00 there; New York (EDT) is 13:00; Sydney (AEDT) is 04:00 on the 27th; Kolkata is 22:30.
NOW = datetime(2026, 10, 26, 17, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def automation_on(monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(config, "NOTIFICATION_SEND_HOUR", 17)
    monkeypatch.setattr(config, "NOTIFICATION_WEEKLY_CAP", 3)
    monkeypatch.setattr(config, "NOTIFICATION_STALE_HOURS", 12)


@pytest.fixture
def expo():
    """Fake Expo client at the lowest layer, so Notification/ticket rows are the real ones."""
    client = MagicMock()

    def publish(messages):
        tickets = []
        for m in messages:
            t = MagicMock()
            t.id = f"ticket-{m.to}"
            t.push_message.to = m.to
            t.validate_response.return_value = None
            tickets.append(t)
        return tickets

    client.publish_multiple.side_effect = publish
    with patch("src.services.notifications._get_push_client", return_value=client):
        yield client


def pushed_tokens(expo) -> list[str]:
    return [m.to for call in expo.publish_multiple.call_args_list for m in call[0][0]]


def make_user(db, days_old: float, name: str | None = None, **overrides) -> User:
    name = name or f"u{uuid.uuid4().hex[:8]}"
    fields = dict(
        id=str(uuid.uuid4()), firstname="A", lastname="B", username=name, email=f"{name}@example.com",
        hashed_password="x", is_active=True, created_at=NOW - timedelta(days=days_old),
    )
    user = User(**{**fields, **overrides})
    db.add(user)
    db.flush()
    return user


def add_token(db, user, tz, label=None, updated_days_ago: float = 0) -> str:
    token = f"ExponentPushToken[{label or uuid.uuid4().hex[:10]}]"
    db.add(PushToken(
        token=token, user_id=user.id if user else None, platform="ios", timezone=tz,
        updated_at=NOW - timedelta(days=updated_days_ago),
    ))
    db.flush()
    return token


def add_game(db, user, status="approved") -> Game:
    game = Game(
        id=str(uuid.uuid4()), name="G", description="d", game_type="card", min_players=2, max_players=4,
        duration="short", objective="o", setup="s", rules="r", contributor_id=user.id, status=status,
    )
    db.add(game)
    db.flush()
    return game


def types_for(db, user) -> list[str]:
    return [n.type for n in db.query(Notification).filter_by(user_id=user.id).all()]


class TestKillSwitch:
    def test_disabled_sends_nothing_and_reports_it(self, db, expo, monkeypatch):
        monkeypatch.setattr(config, "NOTIFICATION_AUTOMATION_ENABLED", False)
        user = make_user(db, 2.5)
        add_token(db, user, "Europe/London")

        assert auto.run_tick(db, NOW) == {"enabled": False}
        expo.publish_multiple.assert_not_called()


class TestTimezoneParsing:
    def test_real_zone(self):
        assert auto.parse_zone("Europe/London") is not None

    @pytest.mark.parametrize("bad", [None, "", "Mars/Olympus", "../etc/passwd", "Europe"])
    def test_unusable_names_are_none_not_an_error(self, bad):
        assert auto.parse_zone(bad) is None


class TestLifecycleTiming:
    def test_sends_when_local_hour_matches_and_not_twice(self, db, expo):
        user = make_user(db, 2.5)
        token = add_token(db, user, "Europe/London")

        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [token]
        assert types_for(db, user) == ["lifecycle_day_2_no_submit"]

        # Same hour again (a retried tick, a second replica): the Notification row is the dedupe.
        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [token]

    def test_waits_for_the_devices_own_local_hour(self, db, expo):
        user = make_user(db, 2.5)
        sydney = add_token(db, user, "Australia/Sydney")

        auto.run_tick(db, NOW)  # 04:00 in Sydney
        expo.publish_multiple.assert_not_called()

        auto.run_tick(db, datetime(2026, 10, 26, 6, 0, tzinfo=UTC))  # 17:00 AEDT
        assert pushed_tokens(expo) == [sydney]

    def test_half_hour_zone_is_reached_once_a_day(self, db, expo):
        user = make_user(db, 2.5)
        kolkata = add_token(db, user, "Asia/Kolkata")

        auto.run_tick(db, datetime(2026, 10, 26, 11, 0, tzinfo=UTC))  # 16:30 IST, hour 16
        expo.publish_multiple.assert_not_called()
        auto.run_tick(db, datetime(2026, 10, 26, 12, 0, tzinfo=UTC))  # 17:30 IST, hour 17
        assert pushed_tokens(expo) == [kolkata]

    def test_device_with_no_timezone_is_treated_as_utc(self, db, expo):
        user = make_user(db, 2.5)
        token = add_token(db, user, None)

        auto.run_tick(db, datetime(2026, 10, 26, 16, 0, tzinfo=UTC))
        expo.publish_multiple.assert_not_called()
        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [token]

    def test_only_the_matching_device_of_a_multi_device_user_is_pushed(self, db, expo):
        user = make_user(db, 2.5)
        london = add_token(db, user, "Europe/London")
        add_token(db, user, "America/New_York")

        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [london]


class TestLifecycleAudience:
    def test_missed_ticks_catch_up_but_stale_cohorts_are_dropped(self, db, expo):
        recent = make_user(db, 4.5)   # 2.5 days past the day-2 mark, inside the catch-up window
        old = make_user(db, 20)
        add_token(db, recent, "Europe/London")
        add_token(db, old, "Europe/London")

        auto.run_tick(db, NOW)
        assert "lifecycle_day_2_no_submit" in types_for(db, recent)
        assert types_for(db, old) == []

    def test_day_2_skips_users_who_already_added_a_game(self, db, expo):
        user = make_user(db, 2.5)
        add_token(db, user, "Europe/London")
        add_game(db, user, status="pending")

        auto.run_tick(db, NOW)
        assert "lifecycle_day_2_no_submit" not in types_for(db, user)

    def test_day_3_skips_users_who_already_liked_something(self, db, expo):
        author = make_user(db, 40)
        game = add_game(db, author)
        user = make_user(db, 3.5)
        add_token(db, user, "Europe/London")
        add_game(db, user)  # has submitted, so day 2 does not apply either
        db.add(UserFavourites(game_id=game.id, user_id=user.id))
        db.flush()

        auto.run_tick(db, NOW)
        assert types_for(db, user) == []

    def test_day_7_needs_an_approved_game(self, db, expo):
        approved = make_user(db, 7.5)
        pending = make_user(db, 7.5)
        add_token(db, approved, "Europe/London")
        add_token(db, pending, "Europe/London")
        add_game(db, approved, status="approved")
        add_game(db, pending, status="pending")
        # Likes + games would trigger neither day 2 nor day 3 at this age.

        auto.run_tick(db, NOW)
        assert types_for(db, approved) == ["lifecycle_day_7_submitted"]
        assert types_for(db, pending) == []

    def test_day_14_targets_devices_not_opened_in_ten_days(self, db, expo):
        lapsed = make_user(db, 14.5)
        active = make_user(db, 14.5)
        add_token(db, lapsed, "Europe/London", updated_days_ago=11)
        add_token(db, active, "Europe/London", updated_days_ago=1)

        auto.run_tick(db, NOW)
        assert types_for(db, lapsed) == ["lifecycle_day_14_dormant"]
        assert types_for(db, active) == []

    def test_inactive_and_deleting_users_are_never_pushed(self, db, expo):
        inactive = make_user(db, 2.5, is_active=False)
        deleting = make_user(db, 2.5, deletion_requested_at=NOW - timedelta(days=1))
        add_token(db, inactive, "Europe/London")
        add_token(db, deleting, "Europe/London")

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()


class TestGuardrails:
    def test_one_automated_push_per_user_per_tick(self, db, expo):
        user = make_user(db, 3.5)  # inside both the day-2 and the day-3 window
        add_token(db, user, "Europe/London")

        auto.run_tick(db, NOW)
        assert types_for(db, user) == ["lifecycle_day_2_no_submit"]

        auto.run_tick(db, NOW + timedelta(days=1))  # next day's 17:00
        assert sorted(types_for(db, user)) == ["lifecycle_day_2_no_submit", "lifecycle_day_3_no_like"]

    def test_weekly_cap_blocks_further_pushes(self, db, expo):
        user = make_user(db, 2.5)
        add_token(db, user, "Europe/London")
        for i in range(3):
            db.add(Notification(
                id=str(uuid.uuid4()), user_id=user.id, type=f"campaign_old{i}", title="t", body="b",
                status="sent", created_at=NOW.replace(tzinfo=None) - timedelta(days=2),
            ))
        db.flush()

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()

    def test_transactional_pushes_do_not_count_toward_the_cap(self, db, expo):
        user = make_user(db, 2.5)
        add_token(db, user, "Europe/London")
        for _ in range(5):
            db.add(Notification(
                id=str(uuid.uuid4()), user_id=user.id, type="achievement", title="t", body="b",
                status="sent", created_at=NOW.replace(tzinfo=None) - timedelta(days=1),
            ))
        db.flush()

        auto.run_tick(db, NOW)
        assert "lifecycle_day_2_no_submit" in types_for(db, user)

    def test_a_failing_campaign_does_not_stop_the_others(self, db, expo):
        user = make_user(db, 14.5)
        add_token(db, user, "Europe/London", updated_days_ago=11)

        boom = auto.Campaign("lifecycle_boom", 1, "t", "b", lambda q, nn: 1 / 0)
        with patch.object(auto, "CAMPAIGNS", [boom, *auto.CAMPAIGNS]):
            auto.run_tick(db, NOW)

        assert types_for(db, user) == ["lifecycle_day_14_dormant"]


def draft(db, *, status="approved", audience="users", send_at=None, local_time=False, **kw):
    row = ScheduledNotification(
        id=str(uuid.uuid4()), title="Fresh games", body="Look what's new", audience=audience,
        send_at=(send_at or NOW).replace(tzinfo=None), local_time=local_time, status=status, **kw,
    )
    db.add(row)
    db.flush()
    return row


class TestQueue:
    def test_draft_never_sends_even_when_due(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Europe/London")
        row = draft(db, status="draft")

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()
        assert row.status == "draft"

    def test_approved_utc_row_sends_once_then_is_marked_sent(self, db, expo):
        user = make_user(db, 30)
        token = add_token(db, user, "Europe/London")
        row = draft(db, data=json.dumps({"game_id": "g1"}))

        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [token]
        assert row.status == "sent" and row.sent_at is not None
        note = db.query(Notification).filter_by(user_id=user.id).one()
        assert note.type == f"campaign_{row.id}" and note.data == '{"game_id": "g1"}'

        auto.run_tick(db, NOW + timedelta(hours=1))
        assert pushed_tokens(expo) == [token]

    def test_not_due_yet(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Europe/London")
        row = draft(db, send_at=NOW + timedelta(hours=2))

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()
        assert row.status == "approved"

    def test_row_past_the_stale_window_is_expired_not_sent_late(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Europe/London")
        row = draft(db, send_at=NOW - timedelta(hours=13))

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()
        assert row.status == "expired"

    def test_audience_users_excludes_signed_out_devices_and_devices_excludes_users(self, db, expo):
        user = make_user(db, 30)
        signed_in = add_token(db, user, "Europe/London")
        anon = add_token(db, None, "Europe/London")

        draft(db, audience="users")
        auto.run_tick(db, NOW)
        assert pushed_tokens(expo) == [signed_in]

        expo.publish_multiple.reset_mock()
        draft(db, audience="devices")
        auto.run_tick(db, NOW + timedelta(minutes=1))
        assert pushed_tokens(expo) == [anon]

    def test_queue_pushes_respect_the_weekly_cap(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Europe/London")
        for i in range(3):
            db.add(Notification(
                id=str(uuid.uuid4()), user_id=user.id, type=f"lifecycle_old{i}", title="t", body="b",
                status="sent", created_at=NOW.replace(tzinfo=None) - timedelta(days=1),
            ))
        db.flush()
        draft(db)

        auto.run_tick(db, NOW)
        expo.publish_multiple.assert_not_called()


class TestLocalTimeRows:
    SEND_AT = datetime(2026, 10, 26, 17, 0, tzinfo=UTC)  # read as 17:00 wall-clock in every zone

    def test_each_zone_gets_it_at_its_own_17_00_and_only_once(self, db, expo):
        sydney_user, london_user = make_user(db, 30), make_user(db, 30)
        sydney = add_token(db, sydney_user, "Australia/Sydney")
        london = add_token(db, london_user, "Europe/London")
        row = draft(db, local_time=True, send_at=self.SEND_AT)

        auto.run_tick(db, datetime(2026, 10, 26, 5, 0, tzinfo=UTC))  # Sydney 16:00, London 05:00
        expo.publish_multiple.assert_not_called()

        auto.run_tick(db, datetime(2026, 10, 26, 6, 0, tzinfo=UTC))  # Sydney 17:00
        assert pushed_tokens(expo) == [sydney]

        auto.run_tick(db, datetime(2026, 10, 26, 6, 0, tzinfo=UTC) + timedelta(minutes=5))
        assert pushed_tokens(expo) == [sydney]  # zone already done

        auto.run_tick(db, self.SEND_AT)  # London 17:00
        assert pushed_tokens(expo) == [sydney, london]
        assert json.loads(row.sent_zones) == ["Australia/Sydney", "Europe/London"]

    def test_zone_that_missed_its_window_is_skipped_not_pushed_at_4am(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Australia/Sydney")
        row = draft(db, local_time=True, send_at=self.SEND_AT)

        auto.run_tick(db, self.SEND_AT)  # Sydney is 04:00 the next day, 11h late
        expo.publish_multiple.assert_not_called()

        auto.run_tick(db, self.SEND_AT + timedelta(days=1))  # every zone's window has closed
        assert row.status == "expired"

    def test_row_finishes_as_sent_once_all_zone_windows_close(self, db, expo):
        user = make_user(db, 30)
        add_token(db, user, "Europe/London")
        row = draft(db, local_time=True, send_at=self.SEND_AT)

        auto.run_tick(db, self.SEND_AT)
        assert row.status == "approved"  # still open for zones that have not reached 17:00
        auto.run_tick(db, self.SEND_AT + timedelta(days=1))
        assert row.status == "sent"


class TestHealth:
    def test_quiet_when_nothing_is_wrong(self, db):
        assert auto.health_warnings(db) == []

    def test_flags_invalid_timezone_names(self, db):
        db.add(PushToken(token="ExponentPushToken[h1]", platform="ios", timezone_error="Mars/Olympus"))
        db.commit()
        assert any("IANA" in p for p in auto.health_warnings(db))

    def test_flags_an_approved_row_that_was_never_sent(self, db):
        db.add(ScheduledNotification(id="stuck", title="t", body="b", audience="users", local_time=False,
                                     status="approved", send_at=datetime(2026, 1, 1)))
        db.commit()
        assert any("never sent" in p for p in auto.health_warnings(db, datetime(2026, 1, 10, tzinfo=timezone.utc)))

    def test_log_health_swallows_check_errors_but_logs_them(self, db, caplog):
        with patch.object(auto, "health_warnings", side_effect=RuntimeError("boom")):
            assert auto.log_health(db) == []
        assert "health check failed" in caplog.text
