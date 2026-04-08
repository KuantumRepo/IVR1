import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.redis import redis_client

router = APIRouter()

@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await websocket.accept()
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
