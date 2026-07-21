"""Live smoke test for the Photos R2 + OpenAI-moderation integration.

Every unit test mocks boto3 and the OpenAI SDK, and register's moderation is
FAIL-CLOSED — so a broken integration (wrong request shape, OpenAI can't fetch
a presigned R2 URL, wrong category attribute names, bad R2 credentials) shows up
identically as "photo rejected", with no error. This script bypasses fail-closed
and surfaces raw exceptions, then asserts a KNOWN-SAFE image PASSES end to end.

Run only after provisioning both R2 buckets + the six R2_* env vars and a real
OPENAI_API_KEY:

    python scripts/smoke_photos.py

Expected: exercises presign PUT -> upload -> head -> presign GET -> OpenAI
moderation (must return NOT flagged) -> copy_to_public -> delete, and prints
"SMOKE PASS". Any failure raises loudly instead of being swallowed.
"""
import base64
import os
import uuid
import urllib.request

from dotenv import load_dotenv

load_dotenv("/Users/maxswaine/development/python/GamesRepository/.env")

from openai import OpenAI

from src.services import storage

# A 1x1 white PNG — deterministic, unambiguously safe content.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

object_key = f"games/smoke-{uuid.uuid4().hex}/test.png"

print("1. presign PUT to quarantine...")
put_url = storage.generate_quarantine_put(object_key, "image/png")

print("2. upload bytes to quarantine...")
req = urllib.request.Request(put_url, data=PNG_BYTES, method="PUT",
                             headers={"Content-Type": "image/png"})
with urllib.request.urlopen(req) as resp:
    assert resp.status in (200, 204), f"PUT failed: {resp.status}"

print("3. head_quarantine...")
info = storage.head_quarantine(object_key)
assert info is not None, "head_quarantine returned None — object not found or bad credentials"
print("   size:", info["size"], "type:", info["content_type"])

print("4. presign GET + OpenAI moderation (surfacing exceptions)...")
get_url = storage.generate_quarantine_get(object_key)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
response = client.moderations.create(
    model="omni-moderation-2024-09-26",
    input=[{"type": "image_url", "image_url": {"url": get_url}}],
)
c = response.results[0].categories
# Assert the exact attribute names check_image relies on actually exist:
for attr in ("sexual", "sexual_minors", "violence_graphic", "hate", "hate_threatening"):
    assert hasattr(c, attr), f"category attribute missing: {attr}"
flagged = c.sexual or c.sexual_minors or c.violence_graphic or c.hate or c.hate_threatening
assert not flagged, "known-safe 1x1 PNG was flagged — moderation wiring is wrong"
print("   moderation OK — safe image not flagged, all category attrs present")

print("5. copy_to_public + verify public URL reachable...")
storage.copy_to_public(object_key)
public_url = storage.public_url_for(object_key)
with urllib.request.urlopen(public_url) as resp:
    assert resp.status == 200, f"public URL not reachable: {resp.status}"
print("   public_url:", public_url)

print("6. cleanup...")
storage.delete_public(object_key)
storage.delete_quarantine(object_key)

print("\nSMOKE PASS — R2 round-trip and OpenAI image moderation both work end to end.")
