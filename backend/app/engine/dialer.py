import asyncio
import json
import logging
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.future import select
from sqlalchemy import func, text, update
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

        # ── Stale Lock Reaper ─────────────────────────────────────────────
        # If the backend crashed mid-campaign, rows with locked_by set and
        # locked_at older than LOCK_EXPIRY are abandoned — unlock them so
        # they re-enter the queue automatically without manual pause/resume.
        LOCK_EXPIRY_SECONDS = 300  # 5 minutes
        stale_cutoff = now - timedelta(seconds=LOCK_EXPIRY_SECONDS)
        stale_result = await db.execute(
            update(DialQueue)
            .where(DialQueue.campaign_id == campaign.id)
            .where(DialQueue.locked_by != None)  # noqa: E711
            .where(DialQueue.locked_at < stale_cutoff)
            .values(locked_by=None, locked_at=None)
        )
        if stale_result.rowcount > 0:
            await db.commit()
            logger.warning(
                f"Reaped {stale_result.rowcount} stale locked queue item(s) "
                f"for campaign {campaign.id}"
            )

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
            # Reserve the slot BEFORE originate to prevent the next tick
            # from over-provisioning.  If originate fails, _initiate_call
            # rolls back via DECR.
            await redis_client.incr(redis_key)
            await db.commit()

            # CALL_STARTED is published inside _initiate_call AFTER
            # confirmed originate dispatch — no more phantom events.
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

        redis_key = f"campaign_active:{campaign.id}"
        try:
            # Genesis Inbound sends one-shot bgapi command without blocking the event loop
            result = await esl_manager.bgapi(cmd)

            # ── CRITICAL: Detect originate failures ─────────────────────────
            # bgapi returns error TEXT (e.g. "-ERR USER_NOT_REGISTERED"), NOT
            # a Python exception.  If we don't check, the Redis counter stays
            # inflated (incr'd in _process_campaign) but never decr'd because
            # FreeSWITCH never creates a channel → no CHANNEL_HANGUP_COMPLETE
            # → counter permanently stuck → capacity=0 → dialer stalls.
            result_str = str(result).strip() if result else ""
            is_error = (
                not result
                or result_str.startswith("-ERR")
                or "UNALLOCATED_NUMBER" in result_str
                or "USER_NOT_REGISTERED" in result_str
                or "NO_ROUTE_DESTINATION" in result_str
                or "SUBSCRIBER_ABSENT" in result_str
                or "NETWORK_OUT_OF_ORDER" in result_str
            )

            if is_error:
                logger.error(
                    f"Originate FAILED for {item.phone_number}: {result_str}"
                )
                # Roll back the Redis counter that was pre-incremented in
                # _process_campaign — no channel exists to send a hangup.
                current_val = await redis_client.decr(redis_key)
                if current_val is not None and int(current_val) < 0:
                    await redis_client.set(redis_key, 0)

                # Unlock the queue item so it re-enters the pool.
                # Don't delete it — the hangup handler normally cleans up,
                # but no hangup will ever fire for a failed originate.
                async with AsyncSessionLocal() as cleanup_db:
                    q = await cleanup_db.get(DialQueue, item.id)
                    if q:
                        await cleanup_db.delete(q)
                        await cleanup_db.commit()
                return

            logger.info(f"Originate dispatched for {item.phone_number}")
            # Publish CALL_STARTED only AFTER confirmed dispatch —
            # prevents phantom events on the dashboard for failed originates.
            payload = {
                "event": "CALL_STARTED",
                "campaign_id": str(campaign.id),
                "campaign_name": campaign.name,
                "phone_number": item.phone_number,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await publish_event("dashboard_events", json.dumps(payload))
        except Exception as e:
            logger.error(f"Failed to bridge originate call via ESL for {item.phone_number}: {e}")
            # Unlock the phantom lock instance (async, with floor clamping)
            current_val = await redis_client.decr(redis_key)
            if current_val is not None and int(current_val) < 0:
                await redis_client.set(redis_key, 0)


dialer_engine = CampaignDialer()
