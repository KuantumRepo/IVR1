import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import Campaign, ContactList, SipGateway, CallerId, Agent, DialQueue, Contact, CallLog
from app.schemas.campaign import CampaignCreate, CampaignResponse

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

@router.post("/", response_model=CampaignResponse)
async def create_campaign(campaign_in: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign_data = campaign_in.model_dump(exclude={"list_ids", "gateway_ids", "caller_id_ids", "agent_ids"})
    campaign = Campaign(**campaign_data)
    
    # Associate relations dynamically securely
    if campaign_in.list_ids:
        cl_res = await db.execute(select(ContactList).where(ContactList.id.in_(campaign_in.list_ids)))
        campaign.contact_lists = cl_res.scalars().all()
        
    if campaign_in.gateway_ids:
        sg_res = await db.execute(select(SipGateway).where(SipGateway.id.in_(campaign_in.gateway_ids)))
        campaign.sip_gateways = sg_res.scalars().all()
        
    if campaign_in.caller_id_ids:
        cid_res = await db.execute(select(CallerId).where(CallerId.id.in_(campaign_in.caller_id_ids)))
        campaign.caller_ids = cid_res.scalars().all()
        
    if campaign_in.agent_ids:
        ag_res = await db.execute(select(Agent).where(Agent.id.in_(campaign_in.agent_ids)))
        campaign.agents = ag_res.scalars().all()
        
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    
    return campaign

@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    return result.scalars().all()

@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    if campaign.status == "ACTIVE":
        return {"status": "already active"}
        
    # Queue generation strategy
    if campaign.dialed_count == 0:
        # Load contacts from the campaign's associated contact lists via M2M table
        from app.models.core import campaign_contact_lists
        cl_result = await db.execute(
            select(Contact)
            .join(Contact.contact_list)
            .join(campaign_contact_lists, campaign_contact_lists.c.list_id == ContactList.id)
            .where(campaign_contact_lists.c.campaign_id == campaign_id)
        )
        contacts = cl_result.scalars().all()
        
        queues = []
        for c in contacts:
            queues.append(DialQueue(
                campaign_id=campaign_id,
                contact_id=c.id,
                phone_number=c.phone_number
            ))
        
        if queues:
            db.add_all(queues)
        campaign.total_contacts = len(queues)
        
    campaign.status = "ACTIVE"
    await db.commit()
    
    return {"status": "started", "queue_size": campaign.total_contacts}
    
@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign:
        campaign.status = "PAUSED"
        await db.commit()
    return {"status": "paused"}

@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    # Clean dial queue first
    dq_result = await db.execute(select(DialQueue).where(DialQueue.campaign_id == campaign_id))
    for dq in dq_result.scalars().all():
        await db.delete(dq)
    await db.delete(campaign)
    await db.commit()
    return {"status": "deleted"}

@router.get("/{campaign_id}/metrics")
async def get_campaign_metrics(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    camp = result.scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    conversion_rate = 0
    if camp.answered_count > 0:
        conversion_rate = round((camp.transferred_count / camp.answered_count) * 100, 1)

    return {
        "status": camp.status,
        "total": camp.total_contacts,
        "dialed": camp.dialed_count,
        "answered": camp.answered_count,
        "voicemail": camp.voicemail_count,
        "transfers": camp.transferred_count,
        "failed": camp.failed_count,
        "conversion_rate": conversion_rate
    }


@router.get("/{campaign_id}/amd-stats")
async def get_amd_stats(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    AMD performance analytics for a campaign.
    
    Returns classification breakdown, average decision latency,
    which AMD layer made decisions, and campaign mode distribution.
    """
    # Verify campaign exists
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    camp = result.scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Total calls for this campaign
    total_result = await db.execute(
        select(func.count(CallLog.id)).where(CallLog.campaign_id == campaign_id)
    )
    total_calls = total_result.scalar() or 0
    
    if total_calls == 0:
        return {
            "total_calls": 0,
            "human_pct": 0.0,
            "machine_pct": 0.0,
            "unknown_pct": 0.0,
            "avg_decision_ms": 0,
            "layer_breakdown": {"mod_amd": 0, "whisper": 0, "timeout": 0},
            "mode_breakdown": {"A": 0, "B": 0, "C": 0},
        }
    
    # AMD result breakdown
    human_result = await db.execute(
        select(func.count(CallLog.id))
        .where(CallLog.campaign_id == campaign_id)
        .where(CallLog.amd_result == "human")
    )
    human_count = human_result.scalar() or 0
    
    machine_result = await db.execute(
        select(func.count(CallLog.id))
        .where(CallLog.campaign_id == campaign_id)
        .where(CallLog.amd_result == "machine")
    )
    machine_count = machine_result.scalar() or 0
    
    unknown_count = total_calls - human_count - machine_count
    
    # Average decision time (only for calls that have AMD telemetry)
    avg_ms_result = await db.execute(
        select(func.avg(CallLog.amd_decision_ms))
        .where(CallLog.campaign_id == campaign_id)
        .where(CallLog.amd_decision_ms.isnot(None))
    )
    avg_decision_ms = int(avg_ms_result.scalar() or 0)
    
    # Layer breakdown
    layer_breakdown = {"mod_amd": 0, "whisper": 0, "timeout": 0}
    for layer_name in ["mod_amd", "whisper", "timeout"]:
        layer_result = await db.execute(
            select(func.count(CallLog.id))
            .where(CallLog.campaign_id == campaign_id)
            .where(CallLog.amd_layer == layer_name)
        )
        layer_breakdown[layer_name] = layer_result.scalar() or 0
    
    # Mode breakdown (from campaign, not per-call — but useful for the response)
    mode_breakdown = {"A": 0, "B": 0, "C": 0}
    current_mode = camp.campaign_mode.value if camp.campaign_mode else "A"
    mode_breakdown[current_mode] = total_calls
    
    return {
        "total_calls": total_calls,
        "human_pct": round((human_count / total_calls) * 100, 1) if total_calls else 0.0,
        "machine_pct": round((machine_count / total_calls) * 100, 1) if total_calls else 0.0,
        "unknown_pct": round((unknown_count / total_calls) * 100, 1) if total_calls else 0.0,
        "avg_decision_ms": avg_decision_ms,
        "layer_breakdown": layer_breakdown,
        "mode_breakdown": mode_breakdown,
    }
