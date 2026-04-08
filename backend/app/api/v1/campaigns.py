import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import Campaign, ContactList, SipGateway, CallerId, Agent, DialQueue, Contact
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
