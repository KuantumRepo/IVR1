#!/usr/bin/env python3
"""Trigger a test call with a local caller ID via Bitcall."""
import urllib.request
import json
import os
from datetime import datetime, timedelta, timezone
from jose import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
expire = datetime.now(timezone.utc) + timedelta(hours=1)
token = jwt.encode({"sub": "admin", "exp": expire, "iat": datetime.now(timezone.utc)}, JWT_SECRET, algorithm="HS256")

BASE = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Get the first available call script
req = urllib.request.Request(f"{BASE}/call-scripts/", headers=HEADERS)
scripts = json.loads(urllib.request.urlopen(req, timeout=10).read())
if not scripts:
    print("NO SCRIPTS FOUND")
    exit(1)

script_id = scripts[0]["id"]
print(f"Using script: {scripts[0]['name']} ({script_id})")

# Use Bitcall PSTN gateway
gw_id = "a6a3c1f5-f3fc-45ff-a042-f66ffc0b3392"

# Use existing caller IDs — pick one that looks local-ish
# Available: 18007692535, 12128489200, 16464342455, 15122687530, 14168023762
req2 = urllib.request.Request(f"{BASE}/caller-ids/", headers=HEADERS)
cids = json.loads(urllib.request.urlopen(req2, timeout=10).read())

# Prefer a US mobile-looking number (512 Austin or 646 NYC)
cid_id = None
for c in cids:
    num = c["phone_number"]
    # Skip 1-800 numbers — those get flagged
    if not num.startswith("1800") and not num.startswith("18"):
        cid_id = c["id"]
        print(f"Using caller ID: {num} ({c['id']})")
        break

if not cid_id and cids:
    # Fall back to first non-800 number
    for c in cids:
        if "800" not in c["phone_number"][:5]:
            cid_id = c["id"]
            print(f"Fallback caller ID: {c['phone_number']} ({c['id']})")
            break

if not cid_id and cids:
    cid_id = cids[1]["id"]  # Just use the second one (skip 800)
    print(f"Using caller ID: {cids[1]['phone_number']}")

# Make test call
body = json.dumps({
    "script_id": script_id,
    "phone_number": "+18187320828",
    "gateway_id": gw_id,
    "caller_id_id": cid_id,
    "enable_amd": False,
    "campaign_mode": "A"
}).encode()
req4 = urllib.request.Request(f"{BASE}/call-scripts/test-call", data=body, method="POST", headers=HEADERS)
result = json.loads(urllib.request.urlopen(req4, timeout=30).read())
print(f"Test call result: {result}")
print("PICK UP AND PRESS 1!")
