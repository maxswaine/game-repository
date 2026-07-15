from src.core.security import verify_password
from src.db.tables import User
from tests.api.games.helper import create_user
from tests.utils import valid_user_payload


def test_register_under_13_returns_422(client_no_auth):
    payload = valid_user_payload(overrides={"date_of_birth": "2015-01-01"})
    response = client_no_auth.post("/users/register", json=payload)

    assert response.status_code == 422
    assert "13" in response.text


def test_register_password_too_short_returns_422(client_no_auth):
    payload = valid_user_payload(overrides={"password": "short1"})
    response = client_no_auth.post("/users/register", json=payload)

    assert response.status_code == 422
    assert "8 characters" in response.text


def test_register_password_too_long_returns_422(client_no_auth):
    payload = valid_user_payload(overrides={"password": "a" * 129})
    response = client_no_auth.post("/users/register", json=payload)

    assert response.status_code == 422
    assert "128 characters" in response.text


def test_register_duplicate_username_returns_400_not_db_error(client_no_auth):
    payload = valid_user_payload()
    client_no_auth.post("/users/register", json=payload)

    payload2 = valid_user_payload(overrides={"email": "other@example.com"})
    response = client_no_auth.post("/users/register", json=payload2)

    assert response.status_code == 400
    assert response.json()["detail"] == "Username taken"


def test_register_duplicate_email_returns_400_not_db_error(client_no_auth):
    payload = valid_user_payload(overrides={"username": "uniqueuser_a"})
    client_no_auth.post("/users/register", json=payload)

    payload2 = valid_user_payload(overrides={"username": "uniqueuser_b"})
    response = client_no_auth.post("/users/register", json=payload2)

    assert response.status_code == 400
    assert response.json()["detail"] == "User already registered with this email"

def test_create_user_success(client_no_auth, db):
    payload = valid_user_payload()
    data = create_user(client_no_auth, payload)

    assert data["username"] == payload["username"]
    assert data["country_of_origin"] == payload["country_of_origin"]

    db_user: User = db.query(User).filter(User.username == payload["username"]).first()
    print(db_user.date_of_birth)
    assert db_user is not None
    assert db_user.firstname == payload["firstname"]
    assert db_user.lastname == payload["lastname"]
    assert db_user.email == payload["email"]
    assert db_user.username == payload["username"]
    assert db_user.country_of_origin == payload["country_of_origin"]
    assert db_user.date_of_birth == payload["date_of_birth"]
    assert verify_password(payload["password"], db_user.hashed_password) is True


def test_duplicate_email_violates_db_constraint(db):
    from sqlalchemy.exc import IntegrityError

    user1 = User(
        email="constraint-test@example.com",
        username="constrainttest1",
        firstname="A",
        lastname="B",
        hashed_password="hashed",
    )
    db.add(user1)
    db.commit()

    user2 = User(
        email="constraint-test@example.com",
        username="constrainttest2",
        firstname="C",
        lastname="D",
        hashed_password="hashed",
    )
    db.add(user2)
    try:
        db.commit()
        assert False, "expected IntegrityError for duplicate email"
    except IntegrityError:
        db.rollback()
