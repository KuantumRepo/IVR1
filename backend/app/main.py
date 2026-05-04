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
    
    Uses a raw TCP ESL connection to bypass Genesis library entirely.
    
    Why not use Genesis: The Genesis library's Protocol.send() pops command
    responses from an asyncio.Queue that accumulates stale responses from
    previous cancelled operations ("queue poisoning"). This causes api()
    calls to return wrong data.
    
    Fix: a minimal raw-TCP ESL client that reads each response inline after
    sending each command. No queue, no background tasks, no poisoning.
    Only used for startup sync (~50 commands).
    
    Also reconciles the agent XML directory: purges stale XML files for
    agents that were deleted from the database.
    """
    import asyncio
    from pathlib import Path
    from app.core.database import AsyncSessionLocal
    from app.core.config import settings
    from app.models.core import Agent
    from sqlalchemy.future import select

    # Wait for FS to be ready
    await asyncio.sleep(5)

    async def _raw_esl_session():
        """Raw TCP ESL client — sends commands, reads responses inline.
        
        ESL protocol (inbound):
        1. FS sends "Content-Type: auth/request"
        2. We send "auth <password>"
        3. FS sends "Content-Type: command/reply" with "+OK accepted"
        4. For each command: send "api <cmd>\\n\\n", read response headers + body
        """
        reader, writer = await asyncio.open_connection(
            settings.FS_ESL_HOST, settings.FS_ESL_PORT
        )
        
        async def read_event() -> dict:
            """Read one ESL event (headers + optional body)."""
            headers = {}
            while True:
                line = await reader.readline()
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    break
                if ":" in line:
                    key, val = line.split(":", 1)
                    headers[key.strip()] = val.strip()
            
            # Read body if Content-Length is present
            body = ""
            if "Content-Length" in headers:
                length = int(headers["Content-Length"])
                raw = await reader.readexactly(length)
                body = raw.decode("utf-8", errors="replace")
            
            headers["body"] = body
            return headers
        
        # 1. Read auth/request
        await read_event()
        
        # 2. Authenticate
        writer.write(f"auth {settings.FS_ESL_PASSWORD}\n\n".encode())
        await writer.drain()
        auth_resp = await read_event()
        if "+OK" not in auth_resp.get("Reply-Text", ""):
            raise ConnectionError("ESL auth failed")
        
        async def send_api(cmd: str) -> str:
            """Send an api command and return the response body."""
            writer.write(f"api {cmd}\n\n".encode())
            await writer.drain()
            resp = await read_event()
            return resp.get("body", "").strip()
        
        return reader, writer, send_api

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Agent))
            agents = result.scalars().all()
            
            # ── Reconcile agent XML directory ─────────────────────────────
            db_extensions = set()
            for agent in agents:
                ext = agent.sip_extension or agent.phone_or_sip
                db_extensions.add(str(ext))
            
            agent_dir = Path(settings.FS_CONF_DIR) / "directory" / "default"
            if agent_dir.exists():
                for xml_file in agent_dir.glob("*.xml"):
                    ext_name = xml_file.stem
                    if ext_name not in db_extensions:
                        xml_file.unlink()
                        logger.info(f"Purged orphaned agent XML: {xml_file.name}")
            
            if not agents:
                logger.info("No agents to sync into mod_callcenter")
                return
        
        # ── Open raw ESL connection and sync agents ───────────────────────
        reader, writer, send_api = await _raw_esl_session()
        logger.info("Agent sync: raw ESL connection established (bypassing Genesis)")
        
        for agent in agents:
            ext = agent.sip_extension or agent.phone_or_sip
            try:
                # Delete first to reset status to default (Logged Out).
                # mod_callcenter's API parser splits on spaces, so multi-word
                # statuses (Logged Out, On Break) CANNOT be set via api commands.
                # Workaround: delete → add (defaults to Logged Out) → only set
                # Available for agents whose softphone is actually registered.
                await send_api(f"callcenter_config agent del {ext}")
                await send_api(f"callcenter_config agent add {ext} Callback")
                await send_api(f"callcenter_config agent set contact {ext} user/{ext}")
                await send_api(f"callcenter_config agent set state {ext} Waiting")
                await send_api(f"callcenter_config tier add internal_sales_queue {ext} 1 1")
                
                # Check registration — only promote to Available if registered
                reg_result = await send_api(f"sofia_contact user/{ext}")
                is_registered = bool(reg_result) and "error" not in reg_result.lower()
                
                if is_registered:
                    await send_api(f"callcenter_config agent set status {ext} Available")
                    logger.info(f"Agent {ext}: registered → Available")
                else:
                    # Agent stays at default 'Logged Out' — won't receive calls
                    logger.info(f"Agent {ext}: not registered → Logged Out (default)")
            except Exception as e:
                logger.error(f"Failed to sync agent {ext}: {e}", exc_info=True)
        
        logger.info(f"Synced {len(agents)} agent(s) into mod_callcenter")
        
        # Close raw connection
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        logger.error(f"Agent sync failed: {e}", exc_info=True)


async def _registration_event_watcher():
    """Dedicated ESL event listener for SIP registration lifecycle.
    
    FreeSWITCH recommended pattern: a persistent inbound ESL connection
    subscribing to CUSTOM sofia::register and sofia::unregister events.
    When an agent's softphone connects/disconnects, we update their
    mod_callcenter status accordingly:
    
      - sofia::register   → callcenter_config agent set status <ext> Available
      - sofia::unregister → callcenter_config agent set status <ext> 'Logged Out'
    
    Why a separate connection: Genesis Consumer's event delivery is unreliable
    for CUSTOM subclass events. Using raw TCP ESL with explicit 'event plain CUSTOM'
    subscription guarantees we receive these events.
    
    Uses api (foreground) commands on the SAME connection — no pool poisoning risk
    since this connection is dedicated and serialized.
    """
    import asyncio
    import urllib.parse
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.models.core import Agent
    from sqlalchemy.future import select
    
    # Wait for FS to be fully ready (after agent sync completes)
    await asyncio.sleep(12)
    
    # Cache known agent extensions for filtering (refresh periodically)
    known_extensions: set[str] = set()
    
    async def _refresh_known_extensions():
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Agent))
                agents = result.scalars().all()
                known_extensions.clear()
                for a in agents:
                    ext = a.sip_extension or a.phone_or_sip
                    known_extensions.add(str(ext))
        except Exception as e:
            logger.warning(f"Registration watcher: failed to refresh extensions: {e}")
    
    await _refresh_known_extensions()
    
    backoff = 5
    while True:
        try:
            reader, writer = await asyncio.open_connection(
                settings.FS_ESL_HOST, settings.FS_ESL_PORT
            )
            logger.info("Registration watcher: raw ESL connection established")
            backoff = 5  # Reset backoff on successful connect
            
            async def read_event() -> dict:
                headers = {}
                while True:
                    line = await reader.readline()
                    if not line:
                        raise ConnectionError("ESL connection closed")
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line:
                        break
                    if ":" in line:
                        key, val = line.split(":", 1)
                        headers[key.strip()] = val.strip()
                body = ""
                if "Content-Length" in headers:
                    length = int(headers["Content-Length"])
                    raw = await reader.readexactly(length)
                    body = raw.decode("utf-8", errors="replace")
                headers["_body"] = body
                return headers
            
            # 1. Authenticate
            await read_event()  # auth/request
            writer.write(f"auth {settings.FS_ESL_PASSWORD}\n\n".encode())
            await writer.drain()
            auth_resp = await read_event()
            if "+OK" not in auth_resp.get("Reply-Text", ""):
                raise ConnectionError("ESL auth failed for registration watcher")
            
            # 2. Subscribe to CUSTOM events (sofia register/unregister)
            # This is the FreeSWITCH-standard way to receive registration events
            writer.write(b"event plain CUSTOM sofia::register sofia::unregister\n\n")
            await writer.drain()
            sub_resp = await read_event()
            logger.info(f"Registration watcher: subscribed to sofia events: {sub_resp.get('Reply-Text', '')}")
            
            # Periodic extension refresh counter
            event_count = 0
            
            # 3. Event loop — process registration events
            while True:
                event = await read_event()
                content_type = event.get("Content-Type", "")
                
                # The event body contains the actual event data as key-value pairs
                if content_type == "text/event-plain":
                    body = event.get("_body", "")
                    # Parse the event body into a dict
                    ev = {}
                    for line in body.split("\n"):
                        if ":" in line:
                            k, v = line.split(":", 1)
                            ev[k.strip()] = urllib.parse.unquote(v.strip())
                    
                    subclass = ev.get("Event-Subclass", "")
                    ext = ev.get("from-user", "")
                    
                    if not ext:
                        continue
                    
                    # Only process known agent extensions (ignore random SIP scanners)
                    if ext not in known_extensions:
                        continue
                    
                    if subclass == "sofia::register":
                        logger.info(f"Registration watcher: {ext} registered → setting Available")
                        writer.write(f"api callcenter_config agent set status {ext} Available\n\n".encode())
                        await writer.drain()
                        await read_event()  # Read command response
                        
                    elif subclass == "sofia::unregister":
                        logger.info(f"Registration watcher: {ext} unregistered → setting Logged Out")
                        writer.write(f"api callcenter_config agent set status {ext} 'Logged Out'\n\n".encode())
                        await writer.drain()
                        await read_event()  # Read command response
                    
                    # Refresh extensions cache every 100 events
                    event_count += 1
                    if event_count % 100 == 0:
                        await _refresh_known_extensions()
                        
        except Exception as e:
            logger.warning(f"Registration watcher: disconnected ({e}). Reconnecting in {backoff}s...")
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # Exponential backoff, max 60s

async def _sync_gateway_xml_on_startup():
    """Regenerate all gateway XML files from the database on startup.
    
    Gateway XML files are persisted on the Docker host volume mount at
    freeswitch/conf/sip_profiles/external/. If the backend code changes
    (e.g. adding dtmf-type or fixing register=false for IP_BASED auth),
    the stale XML files on disk keep the OLD settings, causing:
      - 904 "no matching challenge" for IP-auth trunks still set to register=true
      - Missing dtmf-type causing DTMF failures
    
    This function:
      1. Purges all dynamic gateway XMLs and regenerates from current DB + code
      2. Kills any FreeSWITCH-live gateways that no longer exist in the DB
         (handles crash-during-delete edge cases)
    """
    import asyncio
    from pathlib import Path
    from app.core.database import AsyncSessionLocal
    from app.models.core import SipGateway
    from app.api.v1.sip_gateways import generate_freeswitch_xml
    from app.core.config import settings
    from sqlalchemy.future import select
    
    await asyncio.sleep(3)
    
    try:
        # Use the configured FS_CONF_DIR which maps to the Docker shared volume
        # (./freeswitch/conf:/usr/local/freeswitch/etc/freeswitch:rw)
        gw_dir = Path(settings.FS_CONF_DIR) / "sip_profiles" / "external"
        gw_dir.mkdir(parents=True, exist_ok=True)
        
        # Purge ALL existing gateway XMLs (they may be stale)
        for xml_file in gw_dir.glob("*.xml"):
            xml_file.unlink()
            logger.info(f"Purged stale gateway XML: {xml_file.name}")
        
        # Regenerate from DB
        db_gateway_ids = set()
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SipGateway).where(SipGateway.is_active == True))
            gateways = result.scalars().all()
            
            for gw in gateways:
                db_gateway_ids.add(str(gw.id))
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
        
        # ── Kill stale gateways in FreeSWITCH memory ─────────────────────
        # 'sofia profile external rescan' only ADDS/UPDATES gateways — it
        # does NOT remove deleted ones. We must explicitly killgw each stale
        # gateway that exists in FS but not in the DB.
        await asyncio.sleep(2)  # Give rescan time to settle
        gwlist_raw = await esl_manager.api("sofia profile external gwlist")
        gwlist_str = str(gwlist_raw).strip() if gwlist_raw else ""
        
        if gwlist_str and not gwlist_str.startswith("-ERR"):
            live_gw_ids = set(gwlist_str.split())
            stale_gw_ids = live_gw_ids - db_gateway_ids
            
            for stale_id in stale_gw_ids:
                try:
                    await esl_manager.api(f"sofia profile external killgw {stale_id}")
                    logger.info(f"Killed stale FreeSWITCH gateway: {stale_id}")
                except Exception as e:
                    logger.warning(f"Failed to kill stale gateway {stale_id}: {e}")
            
            if stale_gw_ids:
                logger.info(f"Cleaned up {len(stale_gw_ids)} stale gateway(s) from FreeSWITCH")
            else:
                logger.info("No stale gateways — FreeSWITCH and DB are in sync")
        
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
    
    # Dedicated ESL listener for sofia::register/unregister events.
    # Keeps mod_callcenter agent status in sync with live SIP registrations.
    asyncio.create_task(_registration_event_watcher())
    
    # Purge stale campaign queue XMLs from previous runs.
    # Campaigns will recreate their queues when started via the API.
    from app.engine.queue_manager import QUEUE_DIR
    if QUEUE_DIR.exists():
        for qf in QUEUE_DIR.glob("campaign_*.xml"):
            qf.unlink()
            logger.info(f"Purged stale campaign queue XML: {qf.name}")
    
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
