from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import CallScript, IvrNode, IvrRoute, Campaign, SipGateway, Agent, CallerId, AudioFile, CampaignStatus, CampaignType, CampaignMode
from app.schemas.call_script import CallScriptCreate, CallScriptResponse, TestCallRequest
from app.engine.tts import synthesize_node_prompt
from app.esl.connection import esl_manager

router = APIRouter(prefix="/call-scripts", tags=["Call Scripts"])

@router.post("/", response_model=CallScriptResponse)
async def create_script(script_in: CallScriptCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # 1. Create the top level script
    script_data = script_in.model_dump(exclude={"nodes"})
    script = CallScript(**script_data)
    db.add(script)
    await db.flush() # flush to get script.id
    
    # 2. Map nodes
    # First Pass: Create nodes and flush to DB to get backend UUIDs
    node_map = {} # frontend UUID -> actual DB UUID mapping
    db_nodes = []
    
    for idx, node_in in enumerate(script_in.nodes):
        node = IvrNode(
            script_id=script.id,
            name=node_in.name if node_in.name else f"Node {idx}",
            node_type=node_in.node_type,
            is_start_node=node_in.is_start_node,
            prompt_audio_id=node_in.prompt_audio_id,
            tts_text=node_in.tts_text,
            tts_voice=node_in.tts_voice
        )
        # We do NOT set node.id = node_in.id, allowing Postgres to automatically generate the UUID
        db.add(node)
        db_nodes.append((node_in, node))
        
    await db.flush() # Persist all nodes to db and capture their brand new DB-generated UUIDs
    
    for node_in, db_node in db_nodes:
        if node_in.id:
            node_map[str(node_in.id)] = db_node.id
            
        # Pre-generate TTS in background to eliminate latency on the first live call
        if db_node.tts_text:
            voice = db_node.tts_voice or "af_heart"
            background_tasks.add_task(synthesize_node_prompt, str(db_node.id), db_node.tts_text, voice, force=True)
            
    # Second Pass: Create Routes
    for node_in, db_node in db_nodes:
        for route_in in node_in.routes:
            real_target_id = None
            if route_in.target_node_id:
                frontend_target_str = str(route_in.target_node_id)
                real_target_id = node_map.get(frontend_target_str)

            route = IvrRoute(
                node_id=db_node.id,
                action_type='GO_TO_NODE',
                **route_in.model_dump(exclude={"target_node_id"})
            )
            route.target_node_id = real_target_id
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

@router.get("/{script_id}", response_model=CallScriptResponse)
async def get_script(script_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CallScript)
        .options(selectinload(CallScript.nodes).selectinload(IvrNode.routes))
        .where(CallScript.id == script_id)
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script

@router.put("/{script_id}", response_model=CallScriptResponse)
async def update_script(
    script_id: UUID, 
    script_in: CallScriptCreate, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
        
    script.name = script_in.name
    script.description = script_in.description
    script.script_type = script_in.script_type
    
    # Cascade delete all old nodes
    await db.execute(delete(IvrNode).where(IvrNode.script_id == script_id))
    await db.flush()
    
    # 2. Re-Map nodes
    node_map = {} 
    db_nodes = []
    
    for idx, node_in in enumerate(script_in.nodes):
        node = IvrNode(
            script_id=script.id,
            name=node_in.name if node_in.name else f"Node {idx}",
            node_type=node_in.node_type,
            is_start_node=node_in.is_start_node,
            prompt_audio_id=node_in.prompt_audio_id,
            tts_text=node_in.tts_text,
            tts_voice=node_in.tts_voice
        )
        db.add(node)
        db_nodes.append((node_in, node))
        
    await db.flush() 
    
    for node_in, db_node in db_nodes:
        if node_in.id:
            node_map[str(node_in.id)] = db_node.id
            
        if db_node.tts_text:
            voice = db_node.tts_voice or "af_heart"
            background_tasks.add_task(synthesize_node_prompt, str(db_node.id), db_node.tts_text, voice, force=True)
            
    for node_in, db_node in db_nodes:
        for route_in in node_in.routes:
            real_target_id = None
            if route_in.target_node_id:
                frontend_target_str = str(route_in.target_node_id)
                real_target_id = node_map.get(frontend_target_str)

            route = IvrRoute(
                node_id=db_node.id,
                action_type='GO_TO_NODE',
                **route_in.model_dump(exclude={"target_node_id"})
            )
            route.target_node_id = real_target_id
            db.add(route)
            
    await db.commit()
    
    result = await db.execute(
        select(CallScript)
        .options(selectinload(CallScript.nodes).selectinload(IvrNode.routes))
        .where(CallScript.id == script.id)
    )
    return result.scalar_one()

@router.delete("/{script_id}")
async def delete_script(script_id: UUID, db: AsyncSession = Depends(get_db)):
    # Clean up Test Campaign usage immediately
    await db.execute(delete(Campaign).where(Campaign.name == "[System] Test Environment", Campaign.script_id == script_id))
    
    # Validate no real campaigns are actively bound
    result_active = await db.execute(select(Campaign).where(Campaign.script_id == script_id))
    if result_active.first():
        raise HTTPException(status_code=400, detail="Cannot delete an IVR Script that is actively bound to a live campaign.")

    result = await db.execute(select(CallScript).where(CallScript.id == script_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
        
    await db.delete(script)
    await db.commit()
    return {"status": "deleted"}

@router.post("/test-call")
async def test_call_script(request: TestCallRequest, db: AsyncSession = Depends(get_db)):
    # 1. Acquire or create the System Test Campaign
    result = await db.execute(
        select(Campaign)
        .options(selectinload(Campaign.sip_gateways), selectinload(Campaign.caller_ids), selectinload(Campaign.agents))
        .where(Campaign.name == "[System] Test Environment")
    )
    camp = result.scalar_one_or_none()
    
    if not camp:
        camp = Campaign(
            name="[System] Test Environment",
            script_id=request.script_id,
            status=CampaignStatus.DRAFT,
            enable_amd=request.enable_amd,
            campaign_mode=CampaignMode(request.campaign_mode),
            vm_drop_audio_id=request.vm_drop_audio_id,
        )
        db.add(camp)
    else:
        camp.script_id = request.script_id
        camp.enable_amd = request.enable_amd
        camp.campaign_mode = CampaignMode(request.campaign_mode)
        camp.vm_drop_audio_id = request.vm_drop_audio_id
        
    # Clear existing relations
    camp.sip_gateways = []
    camp.caller_ids = []
    camp.agents = []
    
    # 2. Attach selected components
    if request.gateway_id:
        gw = await db.get(SipGateway, request.gateway_id)
        if gw: camp.sip_gateways.append(gw)
        
    if request.caller_id_id:
        cid = await db.get(CallerId, request.caller_id_id)
        if cid: camp.caller_ids.append(cid)
        
    if request.agent_id:
        agent = await db.get(Agent, request.agent_id)
        if agent: camp.agents.append(agent)
        
    await db.commit()
    
    # 3. Construct Originate Command natively
    clean_target = request.phone_number.strip()
    if clean_target.lower().startswith("sip:"):
        clean_target = clean_target[4:]

    if "@" in clean_target:
        # Direct SIP URI dialing (bypass gateway wrappers)
        dial_string = f"sofia/external/{clean_target}"
    else:
        prefix = "sofia/external/"
        if camp.sip_gateways and camp.sip_gateways[0].id:
            prefix = f"sofia/gateway/{camp.sip_gateways[0].id}/"
        dial_string = f"{prefix}{clean_target}"
        
    caller_id_str = "0000000000"
    if camp.caller_ids:
        caller_id_str = camp.caller_ids[0].phone_number
        
    import uuid
    test_call_id = str(uuid.uuid4())
    
    # Resolve campaign_mode and vm_drop_audio_id for channel variables
    campaign_mode_val = camp.campaign_mode.value if camp.campaign_mode else 'A'
    vm_drop_id_val = str(camp.vm_drop_audio_id) if camp.vm_drop_audio_id else ''
    amd_config_val = ''
    if camp.amd_config:
        import json as json_lib
        amd_config_val = json_lib.dumps(camp.amd_config)
    
    vars = (
        f"{{origination_uuid={test_call_id},"
        f"campaign_id={camp.id},"
        f"campaign_mode={campaign_mode_val},"
        f"vm_drop_audio_id={vm_drop_id_val},"
        f"amd_config={amd_config_val},"
        f"is_test_call=true,"
        f"ignore_early_media=true,"
        f"dtmf_type=rfc2833,"
        f"disable_video=true,"
        f"origination_caller_id_number={caller_id_str}}}"
    )
    
    try:
        from app.core.redis import publish_event
        import json
        from datetime import datetime, timezone
        
        await publish_event("test_logs", json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tag": "SYSTEM",
            "detail": f"Bootstrapping Test Flow bridge to {request.phone_number}"
        }))
        
        await esl_manager.bgapi(f"originate {vars}{dial_string} &park()")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"status": "calling", "test_call_id": test_call_id}

@router.delete("/test-call/{test_call_id}")
async def hangup_test_call(test_call_id: UUID):
    try:
        await esl_manager.bgapi(f"uuid_kill {test_call_id}")
        return {"status": "hungup"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
