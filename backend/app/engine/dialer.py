import asyncio
import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.core import Campaign, DialQueue, CampaignStatus, SipGateway
from app.engine.rate_limiter import RateLimiter
from app.esl.connection import esl_manager
from app.core.redis import publish_event, redis_client
import random

logger = logging.getLogger(__name__)

class CampaignDialer:
    def __init__(self):
        self.active_campaigns = {}
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("Outbound Dialer Core Engine started successfully")
        asyncio.create_task(self._main_loop())

    async def _main_loop(self):
        while self.is_running:
            try:
                # Poll active campaigns dynamically every second
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Campaign)
                        .options(selectinload(Campaign.sip_gateways), selectinload(Campaign.caller_ids))
                        .where(Campaign.status == CampaignStatus.ACTIVE)
                    )
                    active_camps = result.scalars().all()
                    
                    for camp in active_camps:
                        # Instantiate internal worker struct if missing
                        if camp.id not in self.active_campaigns:
                            self.active_campaigns[camp.id] = {
                                "limiter": RateLimiter(float(camp.calls_per_second)),
                                "active_calls": 0,
                                "max_calls": camp.max_concurrent_calls
                            }
                            
                        await self._process_campaign(db, camp)
            except Exception as e:
                logger.error(f"Dialer tick loop exception: {e}")
                
            await asyncio.sleep(1.0) # Tick block

    async def _process_campaign(self, db: AsyncSession, campaign: Campaign):
        state = self.active_campaigns[campaign.id]
        
        # Pull real active calls from fast Redis counter
        redis_key = f"campaign_active:{campaign.id}"
        current_active = redis_client.get(redis_key)
        active_count = int(current_active) if current_active else 0
        
        capacity = state["max_calls"] - active_count
        if capacity <= 0:
            return
            
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(DialQueue)
            .where(DialQueue.campaign_id == campaign.id)
            .where(DialQueue.next_attempt_at <= now)
            .where(DialQueue.locked_by == None)
            .order_by(DialQueue.priority.desc(), DialQueue.created_at.asc())
            .limit(capacity)
        )
        queue_items = result.scalars().all()
        
        for item in queue_items:
            # Adhere strictly to FCC/Global dialing regulation CPS
            await state["limiter"].wait()
            
            # Simple lock to avoid duplicate workers claiming it
            item.locked_by = "engine_worker_1"
            item.locked_at = now
            redis_client.incr(redis_key) # Lock memory immediately
            campaign.dialed_count += 1
            await db.commit()
            
            # Broadcast to web ui
            import json
            payload = {
                "event": "CALL_STARTED",
                "campaign_id": str(campaign.id),
                "campaign_name": campaign.name,
                "phone_number": item.phone_number,
                "timestamp": now.isoformat()
            }
            await publish_event("dashboard_events", json.dumps(payload))
            
            # Non-blocking deployment of the originate payload
            asyncio.create_task(self._initiate_call(campaign, item))

    async def _initiate_call(self, campaign: Campaign, item: DialQueue):
        logger.info(f"Originating outbound bridge to {item.phone_number} on Campaign {campaign.name}")

        # Apply SIP Gateway routing if configured (default to sofia/external)
        prefix = "sofia/external/"
        if campaign.sip_gateways:
            gw = campaign.sip_gateways[0]
            prefix = f"sofia/gateway/{gw.id}/" if gw.id else "sofia/external/"
            
        dial_string = f"{prefix}{item.phone_number}"
        
        # Apply Caller ID if configured (Dynamic Random Rotation)
        caller_id_number = "0000000000"
        if campaign.caller_ids:
            random_cid = random.choice(campaign.caller_ids)
            caller_id_number = random_cid.phone_number
        
        # We uniquely track the resulting call by assigning FreeSWITCH vars
        vars = (
            f"{{campaign_id={campaign.id},"
            f"contact_id={item.contact_id},"
            f"dial_queue_id={item.id},"
            f"contact_phone={item.phone_number},"
            f"ignore_early_media=true,"
            f"absolute_codec_string=PCMU,"
            f"disable_video=true,"
            f"origination_caller_id_number={caller_id_number}}}"
        )
        
        # Park immediately drops the answered call into the FS handling pool where Python catches the event
        cmd = f"originate {vars}{dial_string} &park()"
        
        try:
            # Genesis Inbound sends one-shot bgapi command without blocking the event loop
            result = await esl_manager.bgapi(cmd)
            if result:
                logger.info(f"Originate dispatched for {item.phone_number}")
        except Exception as e:
            logger.error(f"Failed to bridge originate call via ESL for {item.phone_number}: {e}")
            # Unlock the phantom lock instance 
            redis_key = f"campaign_active:{campaign.id}"
            current_val = redis_client.decr(redis_key)
            if current_val < 0:
                redis_client.set(redis_key, 0)

dialer_engine = CampaignDialer()
