import secrets
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.core.config import settings
from app.models.core import Agent
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentCredentials
from app.engine.xml_orchestrator import generate_agent_xml, delete_agent_xml
from app.esl.connection import esl_manager

router = APIRouter(prefix="/agents", tags=["Agents"])


def _generate_sip_password(length: int = 16) -> str:
    """Generate a cryptographically secure SIP password."""
    return secrets.token_urlsafe(length)


def _parse_sofia_registrations(raw: str | None) -> dict[str, dict]:
    """
    Parse the output of 'sofia status profile internal reg' into a dict
    keyed by extension (user id).
    
    Example FS output line:
    Registrations:
    =================================
    Call-ID:     abc123
    User:        1001@10.5.0.3
    Contact:     "1001" <sip:1001@10.0.0.5:5060;...>
    Agent:       MicroSIP/3.21.3
    Status:      Registered(UDP)(unknown) EXP(2024-01-01 ...)
    ...
    =================================
    """
    result = {}
    if not raw:
        return result
    
    # Split into registration blocks
    blocks = re.split(r'={3,}', raw)
    
    current_user = None
    current_agent = None
    current_status = None
    
    for block in blocks:
        lines = block.strip().split('\n')
        user = None
        agent = None
        status = None
        
        for line in lines:
            line = line.strip()
            if line.startswith('User:'):
                # User: 1001@10.5.0.3
                user_part = line.split(':', 1)[1].strip()
                user = user_part.split('@')[0] if '@' in user_part else user_part
            elif line.startswith('Agent:'):
                agent = line.split(':', 1)[1].strip()
            elif line.startswith('Status:'):
                status = line.split(':', 1)[1].strip()
        
        if user and status and 'Registered' in status:
            result[user] = {
                "user_agent": agent,
                "status": status,
            }
    
    return result


@router.post("/", response_model=dict)
async def create_agent(agent_in: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Create an agent with auto-generated SIP credentials."""
    # Check for duplicate extension
    existing = await db.execute(
        select(Agent).where(Agent.sip_extension == agent_in.sip_extension)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Extension {agent_in.sip_extension} is already in use")
    
    # Generate secure password
    sip_password = _generate_sip_password()
    
    agent = Agent(
        name=agent_in.name,
        sip_extension=agent_in.sip_extension,
        sip_password=sip_password,
        phone_or_sip=agent_in.sip_extension,  # backward compat
        concurrent_cap=agent_in.concurrent_cap,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    
    # Generate FreeSWITCH directory XML
    await generate_agent_xml(agent)
    
    # Return agent info + one-time credentials
    return {
        "agent": AgentResponse.model_validate(agent).model_dump(mode="json"),
        "credentials": AgentCredentials(
            sip_extension=agent.sip_extension,
            sip_password=sip_password,
            sip_server=settings.FS_SIP_DOMAIN,
            sip_port=settings.FS_SIP_PORT,
        ).model_dump(),
    }


@router.get("/", response_model=List[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List agents with live SIP registration status from FreeSWITCH."""
    result = await db.execute(select(Agent))
    agents = result.scalars().all()
    
    # Fetch live registrations from FreeSWITCH
    reg_data = await esl_manager.api("sofia status profile internal reg")
    registered_exts = _parse_sofia_registrations(reg_data)
    
    results = []
    for agent in agents:
        resp = AgentResponse.model_validate(agent)
        ext = agent.sip_extension or agent.phone_or_sip
        reg_info = registered_exts.get(ext)
        if reg_info:
            resp.sip_registered = True
            resp.sip_user_agent = reg_info.get("user_agent")
        results.append(resp)
    
    return results


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check live status
    reg_data = await esl_manager.api("sofia status profile internal reg")
    registered_exts = _parse_sofia_registrations(reg_data)
    
    resp = AgentResponse.model_validate(agent)
    ext = agent.sip_extension or agent.phone_or_sip
    reg_info = registered_exts.get(ext)
    if reg_info:
        resp.sip_registered = True
        resp.sip_user_agent = reg_info.get("user_agent")
    
    return resp


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: UUID, agent_in: AgentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    update_data = agent_in.model_dump(exclude_unset=True)
    
    # If extension changes, update phone_or_sip too
    if "sip_extension" in update_data:
        update_data["phone_or_sip"] = update_data["sip_extension"]
    
    for key, value in update_data.items():
        setattr(agent, key, value)
        
    await db.commit()
    await db.refresh(agent)
    
    # Refresh FreeSWITCH XML config
    await generate_agent_xml(agent)
    
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    # Remove from FreeSWITCH
    await delete_agent_xml(agent)
    
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted", "id": agent_id}


@router.post("/{agent_id}/test")
async def test_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    ext = agent.sip_extension or agent.phone_or_sip
    # Ring the agent's softphone and play a tone when they pick up
    cmd = f"originate user/{ext} &playback(tone_stream://%(400,200,400,450))"
    
    try:
        res = await esl_manager.bgapi(cmd)
        if res is None:
            raise HTTPException(status_code=503, detail="FreeSWITCH ESL not reachable")
        return {"status": "Test call initiated", "target": ext}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/reset-password")
async def reset_agent_password(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    """Generate a new SIP password for an agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    new_password = _generate_sip_password()
    agent.sip_password = new_password
    await db.commit()
    await db.refresh(agent)
    
    # Regenerate FS XML with new password
    await generate_agent_xml(agent)
    
    return {
        "credentials": AgentCredentials(
            sip_extension=agent.sip_extension,
            sip_password=new_password,
            sip_server=settings.FS_SIP_DOMAIN,
            sip_port=settings.FS_SIP_PORT,
        ).model_dump(),
    }
