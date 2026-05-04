import secrets
import xml.etree.ElementTree as ET
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


def _parse_sofia_registrations_xml(raw: str | None) -> dict[str, dict]:
    """
    Parse the XML output of 'sofia xmlstatus profile internal reg' into a dict
    keyed by extension (user id).
    
    XML format (confirmed from production FS v1.10):
      <profile>
        <registrations>
          <registration>
            <user>3002@18.218.221.240</user>
            <agent>PortSIP UC Client  Android - v13.2.9</agent>
            <status>Registered(UDP)(unknown) ...</status>
            <sip-auth-user>3002</sip-auth-user>
          </registration>
        </registrations>
      </profile>
    """
    result = {}
    if not raw:
        return result

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return result

    for reg in root.findall('.//registration'):
        user_el = reg.find('user')
        agent_el = reg.find('agent')
        status_el = reg.find('status')
        sip_auth_user_el = reg.find('sip-auth-user')

        if user_el is None or status_el is None:
            continue

        status_text = status_el.text or ''
        if 'Registered' not in status_text:
            continue

        # Use sip-auth-user for the extension (clean, no @domain)
        # Fall back to parsing user@domain
        if sip_auth_user_el is not None and sip_auth_user_el.text:
            ext = sip_auth_user_el.text.strip()
        else:
            user_text = user_el.text or ''
            ext = user_text.split('@')[0] if '@' in user_text else user_text

        result[ext] = {
            "user_agent": agent_el.text.strip() if agent_el is not None and agent_el.text else None,
            "status": status_text.strip(),
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
    """List agents with live SIP registration AND callcenter status from FreeSWITCH."""
    import asyncio
    
    result = await db.execute(select(Agent))
    agents = result.scalars().all()
    
    # ── Raw ESL query for both SIP registration + callcenter status ──
    registered_exts: dict[str, dict] = {}
    cc_agents: dict[str, dict] = {}
    
    try:
        reader, writer = await asyncio.open_connection(
            settings.FS_ESL_HOST, settings.FS_ESL_PORT
        )

        async def read_event() -> dict:
            headers = {}
            while True:
                line = await reader.readline()
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
            headers["body"] = body
            return headers

        # Auth
        await read_event()
        writer.write(f"auth {settings.FS_ESL_PASSWORD}\n\n".encode())
        await writer.drain()
        await read_event()

        # 1) SIP registration (XML)
        writer.write(b"api sofia xmlstatus profile internal reg\n\n")
        await writer.drain()
        sip_resp = await read_event()
        sip_xml = sip_resp.get("body", "")
        registered_exts = _parse_sofia_registrations_xml(sip_xml)

        # 2) Callcenter agent list
        writer.write(b"api callcenter_config agent list\n\n")
        await writer.drain()
        cc_resp = await read_event()
        cc_body = cc_resp.get("body", "")
        
        for line in cc_body.strip().split("\n"):
            if "|" not in line or line.startswith("name"):
                continue
            parts = line.split("|")
            if len(parts) >= 7:
                ext = parts[0]
                cc_agents[ext] = {
                    "status": parts[5],    # Available, Logged Out, On Break
                    "state": parts[6],     # Waiting, Receiving, In a queue call
                }

        writer.close()
        await writer.wait_closed()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Raw ESL agent query failed: {e}")
    
    results = []
    for agent in agents:
        resp = AgentResponse.model_validate(agent)
        ext = agent.sip_extension or agent.phone_or_sip
        
        # SIP registration
        reg_info = registered_exts.get(ext)
        if reg_info:
            resp.sip_registered = True
            resp.sip_user_agent = reg_info.get("user_agent")
        
        # Callcenter status
        cc_info = cc_agents.get(str(ext))
        if cc_info:
            resp.callcenter_status = cc_info.get("status")
            resp.callcenter_state = cc_info.get("state")
        
        results.append(resp)
    
    return results


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check live status
    reg_data = await esl_manager.api("sofia xmlstatus profile internal reg")
    registered_exts = _parse_sofia_registrations_xml(reg_data)
    
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
