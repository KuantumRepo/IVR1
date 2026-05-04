#!/usr/bin/env python3
import urllib.request, json, os, time
from datetime import datetime, timedelta, timezone
from jose import jwt
import subprocess

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
cid = next((c["id"] for c in cids if "818" in c["phone_number"]), cids[0]["id"])

target = "+18187320828"

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
uuid = result["test_call_id"]
print(f"Fired {target} => {uuid}")

print("Waiting 8 seconds for call to answer...")
time.sleep(8)

def get_var(var_name):
    cmd = ["sudo", "docker", "exec", "ivr1-freeswitch-1", "/usr/local/freeswitch/bin/fs_cli", "-p", "z0X3WoErw9AFprB19KiYKhTf", "-x", f"uuid_getvar {uuid} {var_name}"]
    try:
        res = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        return res
    except subprocess.CalledProcessError as e:
        return f"ERROR: {e.output.decode().strip()}"
    except Exception as e:
        return f"ERROR: {str(e)}"

print(f"--- Channel Variables for {uuid} ---")
for v in ["read_codec", "write_codec", "dtmf_type", "rtp_2833_recv_payload", "rtp_2833_send_payload", "remote_media_ip"]:
    print(f"{v}: {get_var(v)}")

print("--- Active Channels ---")
try:
    print(subprocess.check_output(["sudo", "docker", "exec", "ivr1-freeswitch-1", "/usr/local/freeswitch/bin/fs_cli", "-p", "z0X3WoErw9AFprB19KiYKhTf", "-x", "show channels"], stderr=subprocess.STDOUT).decode().strip())
except Exception as e:
    print(f"ERROR getting channels: {e}")
