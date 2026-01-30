from backend.core.security import verify_password, hash_password
from backend.db.tables import User
from backend.db.database import get_db
from tests.utils import valid_user_payload

def test_create_user_success(client_no_auth, db):
    payload = valid_user_payload()
    response = client_no_auth.post("/users/register/", json=payload)

    assert response.status_code == 201
    data = response.json()
    print(data)

    assert data["username"] == payload["username"]
    assert data["country_of_origin"] == payload["country_of_origin"]

    db_user = db.query(User).filter(User.username == payload["username"]).first()
    assert db_user is not None
    assert db_user.firstname == payload["firstname"]
    assert db_user.lastname == payload["lastname"]
    assert db_user.email == payload["email"]
    assert db_user.username == payload["username"]
    assert db_user.country_of_origin == payload["country_of_origin"]
    assert verify_password(payload["password"], db_user.hashed_password) is True
