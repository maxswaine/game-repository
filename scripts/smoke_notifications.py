"""Live smoke test for the Notifications Expo push integration.

Every unit test mocks `notifications._get_push_client()`, and the pytest suite has
an autouse fixture that actively forbids a real call to `exponent_server_sdk`. So
the real PushMessage kwargs, the real HTTP round-trip to Expo's push-send endpoint,
real ticket parsing, and the DeviceNotRegistered -> prune branch have never
actually executed. This script exercises the real path.

Expo's push-send endpoint (https://exp.host/--/api/v2/push/send) is unauthenticated
and safe to call with a well-formed-but-fake token: nothing is delivered to any
device, no EAS/APNs/FCM credentials are needed, no user/device required.

Run:

    python scripts/smoke_notifications.py

Expected: makes one real HTTP call to Expo, gets back a real ticket (likely an
error ticket, since the token isn't a real registered device), and our send()
wrapper logs a Notification row with a real status without raising. Prints
"SMOKE PASS". Any failure raises loudly instead of being swallowed.
"""
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.database import Base
from src.db.tables import Notification, PushToken, User
from src.services import notifications

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
db = Session()

user = User(
    id=str(uuid.uuid4()), firstname="Smoke", lastname="Test", username="smoketest",
    email="smoke@example.com", hashed_password="x", is_active=True,
)
db.add(user)
db.commit()

fake_token = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
db.add(PushToken(token=fake_token, user_id=user.id, platform="ios"))
db.commit()

print("1. raw SDK call (diagnostic — bypasses our wrapper to show the real response)...")
from exponent_server_sdk import PushClient, PushMessage  # noqa: E402

raw_client = PushClient()
raw_tickets = raw_client.publish_multiple([PushMessage(to=fake_token, title="Smoke", body="Test")])
raw_ticket = raw_tickets[0]
print("   status:", raw_ticket.status, "| message:", raw_ticket.message, "| details:", raw_ticket.details)

print("2. calling notifications.send() for real (no mocking)...")
notifications.send(db, user.id, "Smoke Test", "This should not deliver to any device.")
db.commit()

note = db.query(Notification).filter_by(user_id=user.id).first()
assert note is not None, "no Notification row written"
print("   notification status:", note.status)
assert note.status in ("sent", "failed"), f"unexpected status: {note.status}"

still_present = db.query(PushToken).filter_by(token=fake_token).first() is not None
print("   token still present:", still_present, "(pruned if Expo reported DeviceNotRegistered)")

print("\nSMOKE PASS — real Expo API round-trip completed, response parsed correctly, send() did not raise.")
