import asyncio
import websockets
import json
import urllib.request

async def test_ws():
    print("Connecting to WebSocket...")
    try:
        async with websockets.connect("ws://localhost:8000/ws/dashboard") as ws:
            print("Connected!")
            
            # Trigger a redis event. We can do this by publishing to redis directly 
            # or finding an API endpoint that publishes.
            # Let's just publish a test message using python redis client.
            import redis.asyncio as redis
            r = redis.from_url("redis://localhost:6379", decode_responses=True)
            await r.publish("dashboard_events", json.dumps({"type": "test", "msg": "hello"}))
            await r.aclose()
            
            # Wait for message
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            print(f"Received WS message: {msg}")
            
    except Exception as e:
        print(f"WebSocket test failed: {e}")

asyncio.run(test_ws())
