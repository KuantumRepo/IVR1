import asyncio
from genesis import Inbound

async def test():
    try:
        async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
            response = await client.send("api status")
            print("✅ ESL CONNECTION OK")
            print(str(response))
    except Exception as e:
        print(f"❌ ESL FAILED: {e}")

asyncio.run(test())
