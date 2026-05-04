#!/usr/bin/env python3
"""Dry-run verification for IVR1 — runs INSIDE the backend container to bypass auth."""
import urllib.request
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from jose import jwt

# Generate a valid admin JWT using the container's own JWT_SECRET
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
expire = datetime.now(timezone.utc) + timedelta(hours=1)
token = jwt.encode({"sub": "admin", "exp": expire, "iat": datetime.now(timezone.utc)}, JWT_SECRET, algorithm="HS256")

BASE = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": f"Bearer {token}"}

def test(name, url):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"  ✅ Status: 200 OK")
            return data
    except urllib.error.HTTPError as e:
        print(f"  ❌ Status: {e.code} {e.reason}")
        try:
            body = json.loads(e.read())
            print(f"  Body: {body}")
        except:
            pass
        return None
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return None

# Test 1: Agents API
agents = test("Agents API (unified status)", f"{BASE}/agents/")
if agents:
    print(f"  Found {len(agents)} agents:")
    for a in agents:
        ext = a.get("sip_extension", "?")
        sip = "REG" if a.get("sip_registered") else "OFF"
        cc = a.get("callcenter_status") or "—"
        state = a.get("callcenter_state") or "—"
        device = (a.get("sip_user_agent") or "—")[:35]
        print(f"    ext={ext:>5}  SIP={sip:>3}  CC={cc:>12}  Queue={state:>20}  Dev={device}")

# Test 2: Campaigns
campaigns = test("Campaigns List", f"{BASE}/campaigns/")
if campaigns and isinstance(campaigns, list) and len(campaigns) > 0:
    for c in campaigns[:3]:
        cid = c["id"]
        print(f"  Campaign: {c['name']} [{c['status']}]")
        
        # Test 3: Campaign agent status
        astatus = test(f"Campaign Agents ({c['name'][:20]})", f"{BASE}/campaigns/{cid}/agents/status")
        if astatus:
            print(f"  {len(astatus)} agents assigned:")
            for a in astatus:
                print(f"    {a['name']:>15}  ext={a['extension']:>5}  cc={a['status']:>12}  state={a.get('state','?')}")
        
        # Test 4: Metrics
        metrics = test(f"Metrics ({c['name'][:20]})", f"{BASE}/campaigns/{cid}/metrics")
        if metrics:
            print(f"  total={metrics.get('total',0)} dialed={metrics.get('dialed',0)} answered={metrics.get('answered',0)} transfers={metrics.get('transfers',0)}")

print(f"\n{'='*60}")
print("ALL DRY TESTS COMPLETE")
print(f"{'='*60}")
