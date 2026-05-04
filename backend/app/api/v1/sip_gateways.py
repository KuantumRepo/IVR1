import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import SipGateway
from app.schemas.sip_gateway import SipGatewayCreate, SipGatewayUpdate, SipGatewayResponse
from app.esl.connection import esl_manager

router = APIRouter(prefix="/sip-gateways", tags=["SIP Gateways"])

def generate_freeswitch_xml(gateway: SipGateway) -> str:
    """Generate FreeSWITCH external gateway XML for the given SipGateway.
    
    Two auth modes supported:
      PASSWORD:  Standard SIP registration. FreeSWITCH sends a REGISTER to the
                 provider with the given username/password. Gateway state → REGED.
      IP_BASED:  Provider authenticates by source IP. FreeSWITCH does NOT register.
                 Uses 'proxy' (not 'realm') for routing. Gateway state → NOREG.
    """
    gw_id = str(gateway.id)
    server = gateway.sip_server
    
    if gateway.auth_type.value == "IP_BASED":
        # ── IP Authentication ─────────────────────────────────────────────
        # Provider trusts our server's IP — no SIP REGISTER needed.
        # 'proxy' tells FreeSWITCH where to send INVITEs.
        # 'username' is still required for the SIP From header construction.
        # NOTE: Explicitly set dtmf-type to "info" to disable RFC 2833 negotiation.
        # FreeSWITCH defaults to rfc2833 if this is omitted. If negotiated,
        # US carriers (AT&T, Verizon) will actively strip DTMF audio from the 
        # G.711 RTP stream, breaking spandsp_start_dtmf in-band detection.
        return f"""<include>
  <gateway name="{gw_id}">
    <param name="proxy" value="{server}"/>
    <param name="realm" value="{server}"/>
    <param name="username" value="not-used"/>
    <param name="password" value="not-used"/>
    <param name="register" value="false"/>
    <param name="caller-id-in-from" value="true"/>
    <param name="dtmf-type" value="none"/>
    <param name="ping" value="25"/>
  </gateway>
</include>
"""
    else:
        # ── Password (Registration) Authentication ────────────────────────
        # Standard SIP trunk: FreeSWITCH sends REGISTER with credentials.
        username = gateway.sip_username or ""
        password = gateway.sip_password or ""
        return f"""<include>
  <gateway name="{gw_id}">
    <param name="realm" value="{server}"/>
    <param name="username" value="{username}"/>
    <param name="password" value="{password}"/>
    <param name="register" value="true"/>
    <param name="caller-id-in-from" value="true"/>
    <param name="dtmf-type" value="none"/>
    <param name="ping" value="25"/>
  </gateway>
</include>
"""


@router.post("/", response_model=SipGatewayResponse)
async def create_gateway(gateway_in: SipGatewayCreate, db: AsyncSession = Depends(get_db)):
    gateway = SipGateway(**gateway_in.model_dump())
    db.add(gateway)
    await db.commit()
    await db.refresh(gateway)
    
    # 1. Write the XML Config for FreeSWITCH
    xml_content = generate_freeswitch_xml(gateway)
    
    # 2. Tell FreeSWITCH via ESL to reload and register the new gateway instantly
    success = await esl_manager.push_gateway_xml(xml_content, f"{gateway.id}.xml")
    if not success:
        # We can log this but still return the created gateway in DB
        pass
        
    return gateway

@router.get("/", response_model=List[SipGatewayResponse])
async def list_gateways(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SipGateway))
    return result.scalars().all()

@router.get("/status")
async def gateway_status(db: AsyncSession = Depends(get_db)):
    """Return live FreeSWITCH registration status for all gateways.
    
    Queries `sofia status gateway <id>` for each gateway and returns
    the State (REGED/NOREG/FAIL_WAIT/TRYING) and Status (UP/DOWN).
    """
    result = await db.execute(select(SipGateway))
    gateways = result.scalars().all()
    
    statuses = []
    for gw in gateways:
        entry = {
            "id": str(gw.id),
            "name": gw.name,
            "sip_server": gw.sip_server,
            "auth_type": gw.auth_type.value if gw.auth_type else "PASSWORD",
            "sofia_state": "UNKNOWN",
            "sofia_status": "UNKNOWN",
        }
        try:
            raw = await esl_manager.api(f"sofia status gateway {gw.id}")
            if raw:
                for line in str(raw).split("\n"):
                    line = line.strip()
                    if line.startswith("State"):
                        entry["sofia_state"] = line.split("\t")[-1].strip()
                    elif line.startswith("Status"):
                        entry["sofia_status"] = line.split("\t")[-1].strip()
        except Exception:
            pass
        statuses.append(entry)
    
    return statuses

@router.delete("/{gateway_id}")
async def delete_gateway(gateway_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SipGateway).where(SipGateway.id == gateway_id))
    gateway = result.scalar_one_or_none()
    if not gateway:
        raise HTTPException(status_code=404, detail="Gateway not found")
    
    gw_id_str = str(gateway_id)
    import logging
    logger = logging.getLogger(__name__)
    
    # ── Step 1: Delete XML file FIRST (prevents resurrection on rescan/restart)
    import os
    from app.core.config import settings
    xml_path = os.path.join(settings.FS_CONF_DIR, "sip_profiles", "external", f"{gw_id_str}.xml")
    if os.path.exists(xml_path):
        os.remove(xml_path)
        logger.info(f"Gateway {gw_id_str}: XML file deleted from disk")
    
    # ── Step 2: Kill the live gateway in FreeSWITCH (synchronous, not fire-and-forget)
    try:
        kill_result = await esl_manager.api(f"sofia profile external killgw {gw_id_str}")
        logger.info(f"Gateway {gw_id_str}: killgw result: {kill_result}")
    except Exception as e:
        logger.warning(f"Gateway {gw_id_str}: killgw failed: {e}")
    
    # ── Step 3: Force profile rescan to re-read the XML directory (file is gone)
    try:
        await esl_manager.api("sofia profile external rescan")
    except Exception:
        pass
    
    # ── Step 4: Verify it's gone (best-effort, don't block delete on this)
    try:
        verify = await esl_manager.api(f"sofia status gateway {gw_id_str}")
        verify_str = str(verify).strip() if verify else ""
        if "Invalid Gateway" in verify_str or not verify_str:
            logger.info(f"Gateway {gw_id_str}: confirmed removed from FreeSWITCH")
        else:
            logger.warning(f"Gateway {gw_id_str}: may still be alive in FreeSWITCH: {verify_str[:100]}")
    except Exception:
        pass
    
    # ── Step 5: Delete from DB (last, so we can retry cleanup if FS fails)
    await db.delete(gateway)
    await db.commit()
    logger.info(f"Gateway {gw_id_str}: deleted from database")
        
    return {"status": "deleted", "id": gateway_id}
    
@router.post("/{gateway_id}/test")
async def test_gateway(gateway_id: UUID, target_number: str, db: AsyncSession = Depends(get_db)):
    """
    Test a SIP gateway by placing a real originate call.
    
    Supports two destination formats (industry standard):
      - PSTN number (e.g. "18005551212") → routes via sofia/gateway/{id}/{number}
      - SIP URI (e.g. "agentnofour@sip2sip.info") → routes via sofia/external/{uri}
    
    Uses synchronous ESL `api` (not `bgapi`) so we get the real FreeSWITCH
    result (+OK or -ERR) instead of just a queue acknowledgment.
    """
    # 1. Look up gateway
    result = await db.execute(select(SipGateway).where(SipGateway.id == gateway_id))
    gateway = result.scalar_one_or_none()
    if not gateway:
        raise HTTPException(status_code=404, detail="Gateway not found")
    
    # 2. Detect destination type and build dial string
    # Strip any leading "sip:" prefix the user may have included
    clean_target = target_number.strip()
    if clean_target.lower().startswith("sip:"):
        clean_target = clean_target[4:]
    
    if "@" in clean_target:
        # SIP URI → direct call via external profile (no gateway needed)
        dial_string = f"sofia/external/{clean_target}"
    else:
        # PSTN number → route through the gateway trunk
        prefix = gateway.add_prefix if gateway.add_prefix else ""
        formatted_number = f"{prefix}{clean_target}"
        dial_string = f"sofia/gateway/{gateway.id}/{formatted_number}"
    
    # Put a strict 20s ring boundary, and loop the answer tone 3 times before auto-hanging up
    cmd = f"originate {{originate_timeout=20,disable_video=true}}{dial_string} &playback(tone_stream://%(400,200,400,450);loops=3)"
    
    try:
        # Synchronous api call → returns actual result, not just "+OK Job-UUID"
        raw = await esl_manager.api(cmd)
        if raw is None:
            raise HTTPException(status_code=503, detail="FreeSWITCH ESL not reachable — ensure 8021 is mapped")
        
        response_text = str(raw).strip()
        
        # FreeSWITCH api returns "+OK <uuid>" on success, "-ERR <reason>" on failure
        if "+OK" in response_text or response_text.startswith("+OK"):
            return {
                "status": "success",
                "detail": response_text,
                "dial_string": dial_string,
                "gateway": gateway.name,
            }
        else:
            return {
                "status": "failed",
                "detail": response_text,
                "dial_string": dial_string,
                "gateway": gateway.name,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


