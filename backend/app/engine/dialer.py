import asyncio
import json
import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy import func, text
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
        self.active_campaigns: dict[str, dict] = {}
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("Outbound Dialer Core Engine started successfully")
        asyncio.create_task(self._main_loop())

    async def _main_loop(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Campaign)
                        .options(selectinload(Campaign.sip_gateways), selectinload(Campaign.caller_ids))
                        .where(Campaign.status == CampaignStatus.ACTIVE)
                    )
                    active_camps = result.scalars().all()
                    active_ids = {camp.id for camp in active_camps}

                    # Purge stale campaign state for campaigns no longer ACTIVE
                    stale_ids = set(self.active_campaigns.keys()) - active_ids
                    for stale_id in stale_ids:
                        del self.active_campaigns[stale_id]
                        logger.info(f"Dialer: purged stale state for campaign {stale_id}")

                    for camp in active_camps:
                        # Instantiate internal worker struct if missing
                        if camp.id not in self.active_campaigns:
                            self.active_campaigns[camp.id] = {
                                "limiter": RateLimiter(float(camp.calls_per_second)),
                                "max_calls": camp.max_concurrent_calls,
                            }

                        await self._process_campaign(db, camp)
            except Exception as e:
                logger.error(f"Dialer tick loop exception: {e}")

            await asyncio.sleep(1.0)

    async def _process_campaign(self, db: AsyncSession, campaign: Campaign):
        state = self.active_campaigns[campaign.id]

        # Pull real active calls from fast Redis counter (async)
        redis_key = f"campaign_active:{campaign.id}"
        current_active = await redis_client.get(redis_key)
        active_count = int(current_active) if current_active else 0

        capacity = state["max_calls"] - active_count
        if capacity <= 0:
            return

        now = datetime.now(timezone.utc)

        # Atomic queue claim using FOR UPDATE SKIP LOCKED
        # This prevents double-dialing across concurrent ticks or workers
        result = await db.execute(
            select(DialQueue)
            .where(DialQueue.campaign_id == campaign.id)
            .where(DialQueue.next_attempt_at <= now)
            .where(DialQueue.locked_by == None)  # noqa: E711
            .order_by(DialQueue.priority.desc(), DialQueue.created_at.asc())
            .limit(capacity)
            .with_for_update(skip_locked=True)
        )
        queue_items = result.scalars().all()

        if not queue_items:
            # Check if campaign should auto-complete:
            # No more queue items AND no active calls in flight
            remaining = await db.execute(
                select(func.count(DialQueue.id))
                .where(DialQueue.campaign_id == campaign.id)
            )
            remaining_count = remaining.scalar() or 0

            if remaining_count == 0 and active_count == 0:
                campaign.status = CampaignStatus.COMPLETE
                campaign.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(
                    f"Campaign {campaign.id} ({campaign.name}) AUTO-COMPLETED — "
                    f"all {campaign.total_contacts} contacts processed"
                )
                # Clean up Redis counter
                await redis_client.delete(redis_key)
            return

        for item in queue_items:
            # Adhere strictly to FCC/Global dialing regulation CPS
            await state["limiter"].wait()

            # Lock the row — already protected by FOR UPDATE SKIP LOCKED
            item.locked_by = "engine_worker_1"
            item.locked_at = now
            await redis_client.incr(redis_key)
            await db.commit()

            # Broadcast to web ui
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
        # campaign_mode controls AMD behavior (A=hangup machine, B=VM drop, C=conservative)
        # vm_drop_audio_id tells the Lua script which audio to play after beep (Mode B)
        # amd_config carries per-campaign AMD tuning overrides as JSON
        campaign_mode_val = campaign.campaign_mode.value if hasattr(campaign, 'campaign_mode') and campaign.campaign_mode else 'A'
        vm_drop_id_val = str(campaign.vm_drop_audio_id) if campaign.vm_drop_audio_id else ''
        amd_config_val = json.dumps(campaign.amd_config) if campaign.amd_config else ''

        vars = (
            f"{{campaign_id={campaign.id},"
            f"contact_id={item.contact_id},"
            f"dial_queue_id={item.id},"
            f"contact_phone={item.phone_number},"
            f"campaign_mode={campaign_mode_val},"
            f"vm_drop_audio_id={vm_drop_id_val},"
            f"amd_config={amd_config_val},"
            f"ignore_early_media=true,"
            f"absolute_codec_string=PCMU,"
            f"dtmf_type=rfc2833,"
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
            # Unlock the phantom lock instance (async, with floor clamping)
            redis_key = f"campaign_active:{campaign.id}"
            current_val = await redis_client.decr(redis_key)
            if current_val is not None and int(current_val) < 0:
                await redis_client.set(redis_key, 0)


dialer_engine = CampaignDialer()
