import asyncio
import json
import redis.asyncio as redis
from datetime import datetime, timezone

async def blast():
    r = redis.from_url("redis://localhost:6379", decode_responses=True)
    
    events = [
        {
            "event": "CALL_STARTED",
            "campaign_id": "892c38da-563b-4bdb-9df4-12c61afd26f9",
            "campaign_name": "Test Campaign",
            "phone_number": "+15550001111",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        {
            "event": "CALL_STARTED",
            "campaign_id": "892c38da-563b-4bdb-9df4-12c61afd26f9",
            "campaign_name": "Test Campaign",
            "phone_number": "+15550002222",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        {
            "event": "CALL_ENDED",
            "phone_number": "+15550001111",
            "cause": "NORMAL_CLEARING",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    for ev in events:
        await r.publish("dashboard_events", json.dumps(ev))
        await asyncio.sleep(0.5)

    await r.aclose()
    print("Test signals blasted.")

asyncio.run(blast())
