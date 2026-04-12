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
    # Generates a standard FreeSWITCH external SIP Profile segment
    password_param = f'<param name="password" value="{gateway.sip_password}"/>' if gateway.sip_password else ''
    username_param = f'<param name="username" value="{gateway.sip_username}"/>' if gateway.sip_username else ''
    
    # IP-authenticated trunks must NOT register — the provider authenticates
    # by source IP. Sending REGISTER to an IP-auth trunk causes the 904
    # "no matching challenge" error because the provider doesn't issue a
    # SIP challenge at all.
    register = "false" if gateway.auth_type.value == "IP_BASED" else "true"
    
    return f"""<include>
  <gateway name="{str(gateway.id)}">
    <param name="realm" value="{gateway.sip_server}"/>
    {username_param}
    {password_param}
    <param name="register" value="{register}" />
    <param name="caller-id-in-from" value="true"/>
    <param name="ping" value="25" />
    <param name="dtmf-type" value="rfc2833"/>
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

@router.delete("/{gateway_id}")
async def delete_gateway(gateway_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SipGateway).where(SipGateway.id == gateway_id))
    gateway = result.scalar_one_or_none()
    if not gateway:
        raise HTTPException(status_code=404, detail="Gateway not found")
        
    # Delete from DB
    await db.delete(gateway)
    await db.commit()
    
    # Remove the XML file from disk so it doesn't resurrect on FS restart
    import os
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workspace_dir = os.path.dirname(backend_dir)
    xml_path = os.path.join(workspace_dir, "freeswitch", "conf", "sip_profiles", "external", f"{gateway_id}.xml")
    if os.path.exists(xml_path):
        os.remove(xml_path)
    
    # Send kill command to FreeSWITCH to instantly unregister the trunk
    await esl_manager.bgapi(f"sofia profile external killgw {str(gateway_id)}")
        
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
    cmd = f"originate {{originate_timeout=20,disable_video=true,absolute_codec_string=PCMU}}{dial_string} &playback(tone_stream://%(400,200,400,450);loops=3)"
    
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


