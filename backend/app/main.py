from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

async def _sync_agents_to_callcenter():
    """Re-provision all agents from DB into mod_callcenter on startup.
    
    mod_callcenter stores agents in memory — they're lost when FreeSWITCH
    restarts. This function waits for the ESL pool to connect, then
    re-adds every agent with their correct contact string and tier.
    """
    import asyncio
    from app.esl.connection import esl_manager
    from app.core.database import AsyncSessionLocal
    from app.models.core import Agent
    from sqlalchemy.future import select
    
    # Wait for ESL pool to be ready
    await asyncio.sleep(5)
    
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Agent))
            agents = result.scalars().all()
            
            if not agents:
                logger.info("No agents to sync into mod_callcenter")
                return
            
            for agent in agents:
                ext = agent.sip_extension or agent.phone_or_sip
                try:
                    await esl_manager.bgapi(f"callcenter_config agent add {ext} Callback")
                    await esl_manager.bgapi(f"callcenter_config agent set contact {ext} user/{ext}")
                    await esl_manager.bgapi(f"callcenter_config agent set status {ext} 'Available'")
                    await esl_manager.bgapi(f"callcenter_config agent set state {ext} Waiting")
                    await esl_manager.bgapi(f"callcenter_config tier add internal_sales_queue {ext} 1 1")
                except Exception as e:
                    logger.error(f"Failed to sync agent {ext}: {e}")
            
            logger.info(f"Synced {len(agents)} agent(s) into mod_callcenter")
    except Exception as e:
        logger.error(f"Agent sync failed: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.engine.dialer import dialer_engine
    from app.engine.handlers import event_handler
    import asyncio

    # event_handler.start() internally calls esl_manager.start() which
    # launches the Genesis Consumer background task
    asyncio.create_task(event_handler.start())
    asyncio.create_task(dialer_engine.start())
    
    # Re-provision all agents into mod_callcenter after ESL connects
    # (mod_callcenter agents are in-memory — lost on FS restart)
    asyncio.create_task(_sync_agents_to_callcenter())
    
    yield
    
    # Shutdown
    dialer_engine.is_running = False
    from app.esl.connection import esl_manager
    await esl_manager.stop()

app = FastAPI(
    title="Broadcaster API",
    description="Backend for Voice Broadcasting & Press-1 Campaign System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.sip_gateways import router as gateways_router
from app.api.v1.agents import router as agents_router
from app.api.v1.caller_ids import router as caller_ids_router
from app.api.v1.audio import router as audio_router
from app.api.v1.call_scripts import router as call_scripts_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.ws import router as ws_router

app.include_router(gateways_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(caller_ids_router, prefix="/api/v1")
app.include_router(audio_router, prefix="/api/v1")
app.include_router(call_scripts_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(ws_router)

@app.get("/")
async def root():
    return {"message": "Broadcaster API is running", "status": "ok"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "redis": "unchecked", 
        "postgres": "unchecked",
        "freeswitch": "unchecked"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
