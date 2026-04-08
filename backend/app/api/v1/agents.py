from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import Agent
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse
from app.engine.xml_orchestrator import generate_agent_xml, delete_agent_xml
from app.esl.connection import esl_manager

router = APIRouter(prefix="/agents", tags=["Agents"])

@router.post("/", response_model=AgentResponse)
async def create_agent(agent_in: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent = Agent(**agent_in.model_dump())
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    
    # Generate FreeSWITCH static XML registration file
    await generate_agent_xml(agent)
    
    return agent

@router.get("/", response_model=List[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent))
    return result.scalars().all()

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: UUID, agent_in: AgentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    update_data = agent_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)
        
    await db.commit()
    await db.refresh(agent)
    
    # Refresh FreeSWITCH XML config (e.g. if their SIP phone changed)
    await generate_agent_xml(agent)
    
    return agent

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
        
    ext = agent.phone_or_sip
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
