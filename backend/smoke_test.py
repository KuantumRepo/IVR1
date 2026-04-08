"""
Full system smoke test — runs against the live backend at localhost:8000
Tests: root, health, all CRUD endpoints, ESL connection
"""
import asyncio
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"

ENDPOINTS = [
    ("GET", "/",                     "API root"),
    ("GET", "/health",               "Health check"),
    ("GET", "/api/v1/sip-gateways", "SIP Gateways list"),
    ("GET", "/api/v1/agents",        "Agents list"),
    ("GET", "/api/v1/caller-ids",    "Caller IDs list"),
    ("GET", "/api/v1/audio",         "Audio Files list"),
    ("GET", "/api/v1/call-scripts/", "Call Scripts list"),
    ("GET", "/api/v1/contact-lists/","Contacts list"),
    ("GET", "/api/v1/campaigns/",    "Campaigns list"),
]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def test_http(method, path, label):
    url = BASE + path
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            data = json.loads(body)
            if isinstance(data, list):
                detail = f"{len(data)} records"
            elif isinstance(data, dict):
                detail = str(list(data.keys()))[:60]
            else:
                detail = str(data)[:60]
            print(f"  {GREEN}✅ {label:<30}{RESET}  200  {detail}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  {RED}❌ {label:<30}{RESET}  {e.code}")
        return False
    except Exception as e:
        print(f"  {RED}❌ {label:<30}{RESET}  ERROR: {e}")
        return False

async def test_esl():
    try:
        from genesis import Inbound
        async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
            resp = await client.send("api status")
            lines = str(resp).split("\n")
            uptime = next((l for l in lines if "is ready" in l or "uptime" in l.lower()), str(lines[0]))
            print(f"  {GREEN}✅ {'FreeSWITCH ESL':<30}{RESET}  Connected — {uptime.strip()[:60]}")
            return True
    except Exception as e:
        print(f"  {RED}❌ {'FreeSWITCH ESL':<30}{RESET}  {e}")
        return False

async def test_redis():
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url("redis://127.0.0.1:6379")
        await r.ping()
        info = await r.info("server")
        version = info.get("redis_version", "?")
        await r.aclose()
        print(f"  {GREEN}✅ {'Redis':<30}{RESET}  PONG — v{version}")
        return True
    except Exception as e:
        print(f"  {RED}❌ {'Redis':<30}{RESET}  {e}")
        return False

async def test_postgres():
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host="127.0.0.1", port=5432,
            user="broadcaster", password="broadcaster_secret",
            database="broadcaster"
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        print(f"  {GREEN}✅ {'PostgreSQL':<30}{RESET}  {version[:55]}")
        return True
    except Exception as e:
        print(f"  {RED}❌ {'PostgreSQL':<30}{RESET}  {e}")
        return False

async def main():
    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  BROADCASTER — FULL SYSTEM SMOKE TEST{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")
    
    results = []

    print(f"{BOLD}[ Infrastructure ]{RESET}")
    results.append(await test_esl())
    results.append(await test_redis())
    results.append(await test_postgres())

    print(f"\n{BOLD}[ FastAPI Endpoints ]{RESET}")
    for method, path, label in ENDPOINTS:
        results.append(test_http(method, path, label))

    passed = sum(results)
    total  = len(results)
    color  = GREEN if passed == total else (YELLOW if passed > total // 2 else RED)
    
    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  Result: {color}{passed}/{total} checks passed{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())
