from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import CallScript, IvrNode, IvrRoute
from app.schemas.call_script import CallScriptCreate, CallScriptResponse
from app.engine.tts import synthesize_node_prompt

router = APIRouter(prefix="/call-scripts", tags=["Call Scripts"])

@router.post("/", response_model=CallScriptResponse)
async def create_script(script_in: CallScriptCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # 1. Create the top level script
    script_data = script_in.model_dump(exclude={"nodes"})
    script = CallScript(**script_data)
    db.add(script)
    await db.flush() # flush to get script.id
    
    # 2. Map nodes
    # Because of circular target_node_id references, we do this in two passes
    node_map = {} # client-side "name" -> real DB UUID mapping
    
    # First Pass: Create nodes
    for idx, node_in in enumerate(script_in.nodes):
        node = IvrNode(
            script_id=script.id,
            name=node_in.name if node_in.name else f"Node {idx}",
            is_start_node=node_in.is_start_node,
            prompt_audio_id=node_in.prompt_audio_id,
            tts_text=node_in.tts_text,
            tts_voice=node_in.tts_voice
        )
        if node_in.id:
            node.id = node_in.id
        db.add(node)
        await db.flush()
        node_map[node.name] = node.id
        
        # Pre-generate TTS in background to eliminate latency on the first live call
        if node.tts_text:
            voice = node.tts_voice or "af_heart"
            background_tasks.add_task(synthesize_node_prompt, str(node.id), node.tts_text, voice, force=True)
        
        # Attach routes to the session (we might need to map target_node_id if client passed it as UUID,
        # but in this naive pass, we just insert them directly assuming target_node_id is already a valid UUID if passed)
        for route_in in node_in.routes:
            route = IvrRoute(
                node_id=node.id,
                **route_in.model_dump()
            )
            db.add(route)
            
    await db.commit()
    
    result = await db.execute(
        select(CallScript)
        .options(selectinload(CallScript.nodes).selectinload(IvrNode.routes))
        .where(CallScript.id == script.id)
    )
    return result.scalar_one()

@router.get("/", response_model=List[CallScriptResponse])
async def list_scripts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallScript).options(selectinload(CallScript.nodes).selectinload(IvrNode.routes)))
    return result.scalars().all()

@router.delete("/{script_id}")
async def delete_script(script_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
        
    await db.delete(script)
    await db.commit()
    return {"status": "deleted"}
