#!/usr/bin/env python3
import urllib.request, json, os, time
from datetime import datetime, timedelta, timezone
from jose import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
expire = datetime.now(timezone.utc) + timedelta(hours=1)
token = jwt.encode({"sub": "admin", "exp": expire, "iat": datetime.now(timezone.utc)}, JWT_SECRET, algorithm="HS256")
BASE = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Script & Gateway
req = urllib.request.Request(f"{BASE}/call-scripts/", headers=HEADERS)
scripts = json.loads(urllib.request.urlopen(req).read())
script_id = scripts[0]["id"]
gw_id = "a6a3c1f5-f3fc-45ff-a042-f66ffc0b3392" # Bitcall

# Get Caller IDs
req2 = urllib.request.Request(f"{BASE}/caller-ids/", headers=HEADERS)
cids = json.loads(urllib.request.urlopen(req2).read())
cid1 = next((c["id"] for c in cids if "818" in c["phone_number"]), cids[0]["id"])
cid2 = next((c["id"] for c in cids if "310" in c["phone_number"]), cids[1]["id"])

targets = [
    ("+18187320828", cid1),
    ("+13102901556", cid2)
]

uuids = []
for target, cid in targets:
    body = json.dumps({
        "script_id": script_id,
        "phone_number": target,
        "gateway_id": gw_id,
        "caller_id_id": cid,
        "enable_amd": False,
        "campaign_mode": "A"
    }).encode()
    req3 = urllib.request.Request(f"{BASE}/call-scripts/test-call", data=body, method="POST", headers=HEADERS)
    result = json.loads(urllib.request.urlopen(req3).read())
    uuids.append(result["test_call_id"])
    print(f"Fired {target} => {result['test_call_id']}")

print(",".join(uuids))
