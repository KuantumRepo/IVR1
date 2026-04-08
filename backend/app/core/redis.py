import redis.asyncio as redis
import os

# Default fallback if .env is missing
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Create a global Redis client connection
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

async def publish_event(channel: str, message: str):
    """Utility to instantly push events to the Redis bus for WebSockets"""
    try:
        await redis_client.publish(channel, message)
    except Exception as e:
        print(f"Redis publish error: {e}")
