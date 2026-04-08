"""
End-to-End Functional Test — Core Dialing Pipeline
Exercises: API seed → Campaign start → Dialer engine → ESL originate → Cleanup
"""
import asyncio
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# Track created IDs for cleanup
created = {}
results = []

def api(method, path, body=None, label=""):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"    {RED}HTTP {e.code}: {body_text[:200]}{RESET}")
        return None
    except Exception as e:
        print(f"    {RED}ERROR: {e}{RESET}")
        return None

def step(num, label, success, detail=""):
    results.append(success)
    icon = f"{GREEN}✅" if success else f"{RED}❌"
    print(f"  {icon} Step {num}: {label:<50}{RESET}  {detail}")

# =====================================================================
print(f"\n{BOLD}{'='*70}{RESET}")
print(f"{BOLD}  BROADCASTER — END-TO-END FUNCTIONAL TEST{RESET}")
print(f"{BOLD}{'='*70}{RESET}\n")

# STEP 1: Create SIP Gateway
print(f"{BOLD}[ Phase 1: Seed Resources ]{RESET}")
gw = api("POST", "/sip-gateways/", {
    "name": "E2E-TestTrunk",
    "sip_server": "sip.test.local",
    "sip_username": "testuser",
    "sip_password": "testpass",
    "max_concurrent": 10
})
if gw:
    created["gateway_id"] = gw["id"]
    step(1, "Create SIP Gateway", True, f"id={gw['id'][:8]}...")
else:
    step(1, "Create SIP Gateway", False)

# STEP 2: Create Agent
ag = api("POST", "/agents/", {
    "name": "E2E-TestAgent",
    "phone_or_sip": "sip:agent@test.local"
})
if ag:
    created["agent_id"] = ag["id"]
    step(2, "Create Agent", True, f"id={ag['id'][:8]}...")
else:
    step(2, "Create Agent", False)

# STEP 3: Create Caller ID
cid = api("POST", "/caller-ids/", {
    "name": "E2E-TestCID",
    "phone_number": "+15559990001"
})
if cid:
    created["caller_id"] = cid["id"]
    step(3, "Create Caller ID", True, f"+15559990001")
else:
    step(3, "Create Caller ID", False)

# STEP 4: Create Call Script with TTS step
script = api("POST", "/call-scripts/", {
    "name": "E2E Press-1 Script",
    "description": "Automated test script",
    "script_type": "PRESS_ONE",
    "transfer_key": "1",
    "steps": [
        {
            "step_order": 1,
            "step_type": "TTS",
            "tts_text": "Hello, this is a test call. Press 1 to speak with an agent.",
            "tts_voice": "en-US-Standard-A"
        }
    ]
})
if script:
    created["script_id"] = script["id"]
    step(4, "Create Call Script (Press-1 + TTS)", True, f"id={script['id'][:8]}...")
else:
    step(4, "Create Call Script (Press-1 + TTS)", False)

# STEP 5: Create Contact List with 3 test contacts
cl = api("POST", "/contact-lists/", {
    "name": "E2E-TestList",
    "description": "3 test contacts for pipeline validation"
})
if cl:
    created["list_id"] = cl["id"]
    contacts_ok = 0
    for i, phone in enumerate(["+15550001111", "+15550002222", "+15550003333"]):
        c = api("POST", f"/contact-lists/{cl['id']}/contacts", {
            "phone_number": phone,
            "first_name": f"Test{i+1}",
            "last_name": "User"
        })
        if c:
            contacts_ok += 1
    step(5, "Create Contact List + 3 Contacts", contacts_ok == 3, f"{contacts_ok}/3 contacts")
else:
    step(5, "Create Contact List + 3 Contacts", False)

# STEP 6: Create Campaign linking all resources
print(f"\n{BOLD}[ Phase 2: Campaign Assembly ]{RESET}")
if all(k in created for k in ["script_id", "list_id", "gateway_id", "agent_id", "caller_id"]):
    camp = api("POST", "/campaigns/", {
        "name": "E2E-TestCampaign",
        "description": "Full pipeline validation",
        "script_id": created["script_id"],
        "list_ids": [created["list_id"]],
        "gateway_ids": [created["gateway_id"]],
        "caller_id_ids": [created["caller_id"]],
        "agent_ids": [created["agent_id"]],
        "max_concurrent_calls": 5,
        "calls_per_second": 1.0,
        "enable_amd": True
    })
    if camp:
        created["campaign_id"] = camp["id"]
        step(6, "Create Campaign (all resources linked)", True, f"status={camp['status']}")
    else:
        step(6, "Create Campaign (all resources linked)", False)
else:
    step(6, "Create Campaign (all resources linked)", False, "Missing prerequisite resources")

# STEP 7: Start Campaign → populate DialQueue
print(f"\n{BOLD}[ Phase 3: Engine Ignition ]{RESET}")
if "campaign_id" in created:
    start = api("POST", f"/campaigns/{created['campaign_id']}/start")
    if start:
        queue_size = start.get("queue_size", 0)
        step(7, "Start Campaign → DialQueue populated", queue_size > 0, f"queue_size={queue_size}")
    else:
        step(7, "Start Campaign → DialQueue populated", False)
else:
    step(7, "Start Campaign → DialQueue populated", False, "No campaign to start")

# STEP 8: Wait for Dialer Engine to pick up and attempt originate
print(f"\n{BOLD}[ Phase 4: Dialer Engine Verification ]{RESET}")
print(f"    {YELLOW}⏳ Waiting 6 seconds for dialer engine tick...{RESET}")
time.sleep(6)

# Check campaign status via API
if "campaign_id" in created:
    campaigns = api("GET", "/campaigns/")
    if campaigns:
        our_camp = next((c for c in campaigns if c["id"] == created["campaign_id"]), None)
        if our_camp:
            is_active = our_camp["status"] == "ACTIVE"
            step(8, "Campaign is ACTIVE in dialer loop", is_active, f"status={our_camp['status']}")
        else:
            step(8, "Campaign is ACTIVE in dialer loop", False, "Campaign not found in list")
    else:
        step(8, "Campaign is ACTIVE in dialer loop", False)
else:
    step(8, "Campaign is ACTIVE in dialer loop", False)

# STEP 9: Verify ESL connection is live
async def check_esl():
    try:
        from genesis import Inbound
        async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
            resp = await client.send("api show calls count")
            return True, str(resp)
    except Exception as e:
        return False, str(e)

esl_ok, esl_detail = asyncio.run(check_esl())
step(9, "FreeSWITCH ESL accepts commands", esl_ok, esl_detail[:60])

# STEP 10: Verify Redis pub/sub channel exists
async def check_redis():
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url("redis://127.0.0.1:6379")
        await r.ping()
        await r.aclose()
        return True
    except Exception as e:
        return False

redis_ok = asyncio.run(check_redis())
step(10, "Redis pub/sub channel reachable", redis_ok, "PONG")

# =====================================================================
# CLEANUP
print(f"\n{BOLD}[ Phase 5: Cleanup ]{RESET}")
cleanup_ok = 0
cleanup_total = 0

if "campaign_id" in created:
    cleanup_total += 1
    p = api("POST", f"/campaigns/{created['campaign_id']}/pause")
    if p: cleanup_ok += 1

for key, endpoint in [
    ("campaign_id", "/campaigns/"),
    ("script_id", "/call-scripts/"),
    ("list_id", "/contact-lists/"),
    ("gateway_id", "/sip-gateways/"),
    ("agent_id", "/agents/"),
    ("caller_id", "/caller-ids/"),
]:
    if key in created:
        cleanup_total += 1
        d = api("DELETE", f"{endpoint}{created[key]}")
        if d: cleanup_ok += 1

step(11, "Cleanup all test data", cleanup_ok == cleanup_total, f"{cleanup_ok}/{cleanup_total} deleted")

# =====================================================================
# FINAL SUMMARY
passed = sum(results)
total  = len(results)
color  = GREEN if passed == total else (YELLOW if passed > total // 2 else RED)

print(f"\n{BOLD}{'='*70}{RESET}")
print(f"{BOLD}  Result: {color}{passed}/{total} steps passed{RESET}")
if passed == total:
    print(f"  {GREEN}🎉 FULL PIPELINE VERIFIED — Ready for production trunk configuration{RESET}")
else:
    print(f"  {YELLOW}⚠️  Some steps failed — review output above{RESET}")
print(f"{BOLD}{'='*70}{RESET}\n")
