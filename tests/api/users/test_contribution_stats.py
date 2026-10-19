"""Profile stats must count every game, not just the first page of /games/mine.

Regression: the app summed GameRead.upvotes over one unordered, 20-item page of
/games/mine, so an admin with 26 games reported 90 likes instead of 141.
"""
from src.db.tables import Game, User
from src.models.enums.duration_enum import DurationEnum
from src.models.enums.game_type_enum import GameTypeEnum


def _add_games(db, user_id, upvotes):
    for i, votes in enumerate(upvotes):
        db.add(Game(
            name=f"Game {i}", description="d",
            game_type=GameTypeEnum.card.value,
            min_players=2, max_players=4,
            duration=DurationEnum.thirty_to_45_min.value,
            objective="o", setup="s", rules="r",
            status="approved", upvotes=votes, contributor_id=user_id,
        ))
    db.commit()


def test_stats_cover_games_beyond_the_first_page(client_with_auth, db, test_user):
    # 26 games, mirroring the admin account that surfaced the bug
    _add_games(db, test_user.id, [5] * 26)

    me = client_with_auth.get("/users/me").json()

    assert me["games_uploaded"] == 26
    assert me["likes_received"] == 130  # 26 * 5, not the 20 * 5 = 100 a page would give

    # /games/mine still pages at 20 — the stat must not depend on it
    page = client_with_auth.get("/games/mine").json()
    assert len(page) == 20
    assert sum(g["upvotes"] for g in page) == 100


def test_stats_are_zero_for_a_user_with_no_games(client_with_auth):
    me = client_with_auth.get("/users/me").json()
    assert me["games_uploaded"] == 0
    assert me["likes_received"] == 0


def test_my_games_pages_are_ordered_and_do_not_overlap(client_with_auth, db, test_user):
    _add_games(db, test_user.id, list(range(25)))

    first = client_with_auth.get("/games/mine?limit=20&offset=0").json()
    second = client_with_auth.get("/games/mine?limit=20&offset=20").json()

    ids = [g["id"] for g in first] + [g["id"] for g in second]
    assert len(ids) == 25
    assert len(set(ids)) == 25, "paging repeated or skipped a game"


def test_stats_follow_a_game_changing_hands(client_with_auth, db, test_user, second_user):
    """purge.py reassigns a deleted user's public games; the stat must track that."""
    _add_games(db, second_user.id, [7, 8])
    assert client_with_auth.get("/users/me").json()["likes_received"] == 0

    db.query(Game).filter(Game.contributor_id == second_user.id).update(
        {"contributor_id": test_user.id}
    )
    db.commit()
    db.expire_all()

    me = client_with_auth.get("/users/me").json()
    assert me["games_uploaded"] == 2
    assert me["likes_received"] == 15


def test_stats_stay_off_the_auth_hot_path(db, test_user):
    """Deferred: a plain User load must not emit the stat subqueries."""
    db.expire_all()
    statements = []
    from sqlalchemy import event

    def record(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record)
    try:
        db.query(User).filter(User.id == test_user.id).first()
    finally:
        event.remove(db.bind, "before_cursor_execute", record)

    assert statements, "expected a query"
    assert not any("sum(games.upvotes)" in s.lower() for s in statements), (
        f"stat subquery leaked into the default User SELECT: {statements}"
    )
