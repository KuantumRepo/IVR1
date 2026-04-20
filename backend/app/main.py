from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from contextlib import asynccontextmanager

# ── CRITICAL: Configure root logger for ALL application modules ──────────────
# Uvicorn's default LOGGING_CONFIG only adds handlers to "uvicorn.*" loggers.
# Without this, application loggers (app.engine.dialer, app.engine.handlers,
# app.esl.connection, etc.) have NO handler and silently drop ALL output below
# WARNING via Python's lastResort stderr handler.  This made the entire dialer
# engine, ESL connection lifecycle, and originate pipeline completely invisible.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

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

async def _sync_gateway_xml_on_startup():
    """Regenerate all gateway XML files from the database on startup.
    
    Gateway XML files are persisted on the Docker host volume mount at
    freeswitch/conf/sip_profiles/external/. If the backend code changes
    (e.g. adding dtmf-type or fixing register=false for IP_BASED auth),
    the stale XML files on disk keep the OLD settings, causing:
      - 904 "no matching challenge" for IP-auth trunks still set to register=true
      - Missing dtmf-type causing DTMF failures
    
    This function purges all dynamic gateway XMLs and regenerates them from
    the current database state + current code, ensuring consistency.
    """
    import asyncio
    from pathlib import Path
    from app.core.database import AsyncSessionLocal
    from app.models.core import SipGateway
    from app.api.v1.sip_gateways import generate_freeswitch_xml
    from sqlalchemy.future import select
    
    await asyncio.sleep(3)
    
    try:
        # Resolve the gateway XML directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_dir = os.path.dirname(backend_dir)
        gw_dir = Path(workspace_dir) / "freeswitch" / "conf" / "sip_profiles" / "external"
        gw_dir.mkdir(parents=True, exist_ok=True)
        
        # Purge ALL existing gateway XMLs (they may be stale)
        for xml_file in gw_dir.glob("*.xml"):
            xml_file.unlink()
            logger.info(f"Purged stale gateway XML: {xml_file.name}")
        
        # Regenerate from DB
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SipGateway).where(SipGateway.is_active == True))
            gateways = result.scalars().all()
            
            for gw in gateways:
                xml_content = generate_freeswitch_xml(gw)
                filepath = gw_dir / f"{gw.id}.xml"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                register_mode = "IP Auth" if gw.auth_type and gw.auth_type.value == "IP_BASED" else "Register"
                logger.info(f"Generated gateway XML: {gw.name} ({gw.id}) — {register_mode}")
            
            logger.info(f"Regenerated {len(gateways)} gateway XML file(s) from database")
        
        # Tell FreeSWITCH to reload the new XML
        from app.esl.connection import esl_manager
        await esl_manager.api("reloadxml")
        await esl_manager.bgapi("sofia profile external rescan")
        logger.info("FreeSWITCH XML reloaded + external profile rescanned")
        
    except Exception as e:
        logger.error(f"Gateway XML sync failed: {e}", exc_info=True)

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
    
    # Regenerate all gateway XMLs from DB (purges stale files)
    asyncio.create_task(_sync_gateway_xml_on_startup())
    
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

# ── Authentication ────────────────────────────────────────────────────────────
from app.auth import router as auth_router, verify_token
from jose import JWTError

# Auth router is PUBLIC (login, verify, qr)
app.include_router(auth_router)

# JWT middleware — protects every /api/v1/* route
@app.middleware("http")
async def jwt_guard(request: Request, call_next):
    """Enforce JWT authentication on all /api/v1/* routes.
    
    Public endpoints (health, root, auth) are excluded.
    WebSocket connections are also excluded (they have their own auth).
    """
    path = request.url.path
    
    # Public paths — no auth required
    if (
        not path.startswith("/api/v1")
        or path.startswith("/ws")
        or path.endswith("/stream")
    ):
        return await call_next(request)
    
    # Extract Bearer token
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"}
        )
    
    token = auth_header[7:]  # Strip "Bearer "
    try:
        verify_token(token)
    except JWTError:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"}
        )
    
    return await call_next(request)

# ── API Routers ───────────────────────────────────────────────────────────────
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
    health_status = {"status": "healthy", "redis": "unknown", "postgres": "unknown", "freeswitch": "unknown"}
    is_healthy = True

    # Check Redis
    try:
        from app.core.redis import redis_client
        await redis_client.ping()
        health_status["redis"] = "connected"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)[:100]}"
        is_healthy = False

    # Check PostgreSQL
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = f"error: {str(e)[:100]}"
        is_healthy = False

    # Check FreeSWITCH ESL
    try:
        from app.esl.connection import esl_manager
        health_status["freeswitch"] = "connected" if esl_manager.connected else "disconnected"
        if not esl_manager.connected:
            is_healthy = False
    except Exception as e:
        health_status["freeswitch"] = f"error: {str(e)[:100]}"
        is_healthy = False

    health_status["status"] = "healthy" if is_healthy else "degraded"
    return health_status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
