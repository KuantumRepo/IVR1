import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.redis import redis_client

router = APIRouter()


async def _get_total_active_calls() -> int:
    """Sum all campaign_active:* counters from Redis."""
    total = 0
    try:
        async for key in redis_client.scan_iter(match="campaign_active:*"):
            val = await redis_client.get(key)
            if val:
                total += max(0, int(val))
    except Exception:
        pass
    return total


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await websocket.accept()

    # Send initial sync so clients that connect mid-campaign get the
    # true active call count instead of starting at 0.
    try:
        total_active = await _get_total_active_calls()
        sync_payload = json.dumps({
            "event": "DASHBOARD_SYNC",
            "active_calls": total_active,
        })
        await websocket.send_json({"event": sync_payload})
    except Exception as e:
        print(f"WS initial sync error: {e}")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("dashboard_events")
    
    try:
        while True:
            # Poll safely using asyncio loop
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message:
                await websocket.send_json({"event": message["data"]})
            else:
                await asyncio.sleep(0.1) # Yield to the event loop
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error: {e}")
    finally:
        await pubsub.unsubscribe("dashboard_events")

@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    pubsub = redis_client.pubsub()
    channel = f"agent_events:{agent_id}"
    await pubsub.subscribe(channel)
    
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message:
                await websocket.send_json({"event": message["data"]})
            else:
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error {agent_id}: {e}")
    finally:
        await pubsub.unsubscribe(channel)

@router.websocket("/ws/test-logs")
async def test_logs_websocket(websocket: WebSocket):
    await websocket.accept()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("test_logs")
    
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message:
                await websocket.send_json({"event": message["data"]})
            else:
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error test_logs: {e}")
    finally:
        await pubsub.unsubscribe("test_logs")
