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
    
    return f"""<include>
  <gateway name="{str(gateway.id)}">
    <param name="realm" value="{gateway.sip_server}"/>
    {username_param}
    {password_param}
    <param name="register" value="true" />
    <param name="caller-id-in-from" value="true"/>
    <param name="ping" value="25" />
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
    
    # Make sure we have the folder accessible (if not mapped to FreeSWITCH correctly yet it will gracefully fail)
    os.makedirs("/etc/freeswitch/sip_profiles/external", exist_ok=True)
    
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
    
    # Send kill command to FreeSWITCH to instantly unregister the trunk
    await esl_manager.bgapi(f"sofia profile external killgw {str(gateway.id)}")
        
    return {"status": "deleted", "id": gateway_id}
    
@router.post("/{gateway_id}/test")
async def test_gateway(gateway_id: UUID, target_number: str, db: AsyncSession = Depends(get_db)):
    # 1. Look up gateway
    result = await db.execute(select(SipGateway).where(SipGateway.id == gateway_id))
    gateway = result.scalar_one_or_none()
    if not gateway:
        raise HTTPException(status_code=404, detail="Gateway not found")
        
    # 2. Build and fire test call command
    prefix = gateway.add_prefix if gateway.add_prefix else ""
    formatted_number = f"{prefix}{target_number}"
    
    dial_string = f"sofia/gateway/{gateway.id}/{formatted_number}"
    cmd = f"originate {dial_string} &playback(tone_stream://%(400,200,400,450))"
    
    try:
        result = await esl_manager.bgapi(cmd)
        if result is None:
            raise HTTPException(status_code=503, detail="FreeSWITCH ESL not reachable — ensure 8021 is mapped")
        return {"status": "Test call initiated", "target": formatted_number, "gateway": gateway.name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
