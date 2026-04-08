"""
Event Handler — registers FreeSWITCH event callbacks on the Genesis Consumer.

Genesis uses a decorator pattern: @consumer.handle("EVENT_NAME")
We register handlers here and the Consumer dispatches them as events arrive.
"""
import asyncio
import json
import logging
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.core import (
    Campaign, DialQueue, Agent, IvrNode, IvrRoute,
    AudioFile, IvrActionType, Contact, CallLog
)
from app.esl.connection import esl_manager
from app.core.redis import publish_event, redis_client
from app.engine.tts import synthesize_node_prompt

logger = logging.getLogger(__name__)

# Grab the Consumer instance so we can decorate handlers on it
_consumer = esl_manager.consumer


# ─── CHANNEL_ANSWER ───────────────────────────────────────────────────────────

@_consumer.handle("CHANNEL_ANSWER")
async def on_channel_answer(event):
    campaign_id = event.get("variable_campaign_id")
    if not campaign_id:
        return

    uuid = event.get("Unique-ID")
    logger.info(f"Target Answered: {uuid} | Campaign: {campaign_id}")

    async with AsyncSessionLocal() as db:
        try:
            camp = await db.get(Campaign, UUID(campaign_id))
            if camp:
                camp.answered_count += 1
                await db.commit()
                if camp.enable_amd:
                    logger.info(f"Triggering AMD on {uuid}")
                    await esl_manager.api(f"uuid_setvar {uuid} execute_on_answer 'lua amd.lua'")
                else:
                    await _start_human_playlist(uuid, camp)
        except Exception as e:
            logger.error(f"on_channel_answer error: {e}", exc_info=True)


# ─── AMD (CUSTOM) ─────────────────────────────────────────────────────────────

@_consumer.handle("CUSTOM")
async def on_custom_event(event):
    subclass = event.get("Event-Subclass", "")
    
    # -- Agent Sofia Registration Sync --
    if subclass == "sofia::register":
        ext = event.get("from-user")
        if ext:
            logger.info(f"Agent {ext} registered -- marking Available in mod_callcenter")
            await esl_manager.bgapi(f"callcenter_config agent set status {ext} Available")
        return

    if subclass == "sofia::unregister":
        ext = event.get("from-user")
        if ext:
            logger.info(f"Agent {ext} unregistered -- marking Logged Out in mod_callcenter")
            await esl_manager.bgapi(f"callcenter_config agent set status {ext} 'Logged Out'")
        return

    # -- AMD Processing --
    if subclass != "amd::info":
        return

    uuid = event.get("Unique-ID")
    amd_result = event.get("variable_amd_result")
    campaign_id = event.get("variable_campaign_id")

    if not campaign_id:
        return

    logger.info(f"AMD Result on {uuid}: {amd_result}")

    async with AsyncSessionLocal() as db:
        try:
            camp = await db.get(Campaign, UUID(campaign_id))
            if not camp:
                return

            if amd_result == "MACHINE":
                logger.info(f"AMD detected MACHINE on {uuid}")
                if camp.enable_vm_drop and camp.vm_drop_audio_id:
                    # Look up the actual audio file path to play
                    audio_row = await db.get(AudioFile, camp.vm_drop_audio_id)
                    if audio_row and audio_row.file_path:
                        logger.info(f"Playing voicemail drop for {uuid} ({audio_row.file_path})")
                        await esl_manager.bgapi(f"uuid_transfer {uuid} inline 'playback:{audio_row.file_path},hangup:NORMAL_CLEARING'")
                    else:
                        logger.info(f"Voicemail audio file not found for {uuid} — hanging up")
                        await esl_manager.api(f"uuid_kill {uuid}")
                else:
                    logger.info(f"No voicemail drop configured for {uuid} — hanging up")
                    await esl_manager.api(f"uuid_kill {uuid}")
            else:
                await _start_human_playlist(uuid, camp)
        except Exception as e:
            logger.error(f"on_custom_event error: {e}", exc_info=True)


# ─── CHANNEL_BRIDGE (MOD_CALLCENTER SCREEN POP) ───────────────────────────────

@_consumer.handle("CHANNEL_BRIDGE")
async def on_channel_bridge(event):
    cc_agent = event.get("variable_cc_agent")
    if not cc_agent:
        return
        
    caller_num = event.get("variable_contact_phone") or event.get("Caller-Destination-Number", "Unknown")
    campaign_id = event.get("variable_campaign_id", "Unknown")
    
    logger.info(f"mod_callcenter bridged call to agent {cc_agent} (Caller: {caller_num})")
    
    async with AsyncSessionLocal() as db:
        try:
            # Look up the agent based on their extension/sip which is stored in phone_or_sip
            result = await db.execute(select(Agent).where(Agent.phone_or_sip == cc_agent))
            agent = result.scalar_one_or_none()
            if agent:
                payload = {
                    "event": "AGENT_RINGING",
                    "agent_id": str(agent.id),
                    "caller_number": caller_num,
                    "campaign_id": campaign_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await publish_event(f"agent_events:{agent.id}", json.dumps(payload))
                logger.info(f"Published screen pop for Agent {agent.id}")
        except Exception as e:
            logger.error(f"Failed to lookup agent for screen pop: {e}", exc_info=True)


# ─── CHANNEL_HANGUP_COMPLETE ──────────────────────────────────────────────────

@_consumer.handle("CHANNEL_HANGUP_COMPLETE")
async def on_hangup(event):
    queue_id    = event.get("variable_dial_queue_id")
    campaign_id = event.get("variable_campaign_id")
    # FIX #2: capture phone from the ESL event BEFORE any try/except
    # so the variable is available in the publish block regardless of exceptions.
    phone_number = (
        event.get("variable_contact_phone")
        or event.get("Caller-Destination-Number")
        or "Unknown"
    )

    if not queue_id:
        return

    cause = event.get("variable_hangup_cause", "UNKNOWN")
    logger.info(f"Hangup queue_id={queue_id} cause={cause}")
    
    # Release capacity to the system instantaneously
    if campaign_id:
        current_val = redis_client.decr(f"campaign_active:{campaign_id}")
        if current_val < 0:
            redis_client.set(f"campaign_active:{campaign_id}", 0)

    async with AsyncSessionLocal() as db:
        try:
            q_item = await db.get(DialQueue, UUID(queue_id))
            if q_item and campaign_id:
                camp = await db.get(Campaign, UUID(campaign_id))

                if (
                    camp
                    and cause != "NORMAL_CLEARING"
                    and q_item.retry_count < camp.retry_attempts
                ):
                    logger.info(
                        f"Rescheduling {q_item.phone_number} "
                        f"(attempt {q_item.retry_count + 1}/{camp.retry_attempts})"
                    )
                    q_item.retry_count += 1
                    q_item.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        minutes=camp.retry_delay_min
                    )
                    q_item.locked_by = None
                    q_item.locked_at = None
                    await db.commit()
                else:
                    await db.delete(q_item)
                    await db.commit()
                    
            # Insert Call Details Record
            duration = int(event.get("variable_billsec", 0))
            amd_result = event.get("variable_amd_result", "UNKNOWN")
            contact_id = event.get("variable_contact_id")
            
            call_log = CallLog(
                campaign_id=UUID(campaign_id) if campaign_id else None,
                contact_id=UUID(contact_id) if contact_id else None,
                phone_number=phone_number,
                duration=duration,
                hangup_cause=cause,
                amd_result=amd_result
            )
            db.add(call_log)
            await db.commit()

        except Exception as e:
            logger.error(f"on_hangup db error: {e}", exc_info=True)

        # Always publish dashboard event — even if db ops failed
        try:
            payload = {
                "event":        "CALL_ENDED",
                "phone_number": phone_number,
                "cause":        cause,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
            }
            await publish_event("dashboard_events", json.dumps(payload))
        except Exception as e:
            logger.error(f"on_hangup publish error: {e}", exc_info=True)


# ─── IVR ENGINE ───────────────────────────────────────────────────────────────

async def _play_ivr_node(uuid: str, node_id: UUID, session) -> None:
    """
    Resolves the prompt (TTS or audio file) for a node, then fires
    FreeSWITCH play_and_get_digits with a regex derived from the node's routes.
    """
    node = await session.execute(
        select(IvrNode)
        .options(
            selectinload(IvrNode.routes).selectinload(IvrRoute.response_audio),
            selectinload(IvrNode.routes).selectinload(IvrRoute.target_node),
        )
        .where(IvrNode.id == node_id)
    )
    node = node.scalar_one_or_none()
    if not node:
        logger.error(f"_play_ivr_node: node {node_id} not found")
        return

    # Tag the channel so CHANNEL_EXECUTE_COMPLETE knows which node we're on
    await esl_manager.api(f"uuid_setvar {uuid} current_ivr_node_id {node.id}")

    # ── Resolve prompt path ────────────────────────────────────────────────
    prompt_path: str | None = None

    if node.prompt_audio_id:
        # Admin uploaded an audio file — look up its path
        audio_row = await session.execute(
            select(AudioFile).where(AudioFile.id == node.prompt_audio_id)
        )
        audio_row = audio_row.scalar_one_or_none()
        if audio_row and audio_row.file_path:
            prompt_path = audio_row.file_path

    elif node.tts_text:
        # FIX #1: synthesize via Kokoro, cache by node_id
        try:
            voice = node.tts_voice or "af_heart"
            prompt_path = await synthesize_node_prompt(
                node_id=str(node.id),
                text=node.tts_text,
                voice=voice,
            )
        except Exception as e:
            logger.error(f"TTS synthesis failed for node {node.id}: {e}", exc_info=True)

    if not prompt_path:
        logger.error(f"Node {node.id} ({node.name!r}) has no prompt — hanging up {uuid}")
        await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
        return

    # ── Build digit regex from active routes ───────────────────────────────
    valid_keys = [str(r.key_pressed) for r in node.routes if r.key_pressed]
    regex = "^[" + "".join(valid_keys) + "]$" if valid_keys else "^$"

    # play_and_get_digits: min=1 max=1 tries=3 timeout=5000ms terminator=#
    cmd = (
        f"uuid_execute {uuid} play_and_get_digits "
        f"'1 1 3 5000 # {prompt_path} silence_stream://250 digit_rx {regex}'"
    )
    logger.info(f"IVR play_and_get_digits on {uuid} | node={node.name!r} | regex={regex}")
    await esl_manager.bgapi(cmd)


async def _start_human_playlist(uuid: str, campaign: Campaign) -> None:
    """Entrypoint when a human answers — finds the start node and begins the IVR tree."""
    logger.info(f"Starting IVR tree for {uuid} (Campaign {campaign.id})")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(IvrNode)
            .where(IvrNode.script_id == campaign.script_id)
            .where(IvrNode.is_start_node == True)
        )
        start_node = result.scalar_one_or_none()
        if not start_node:
            logger.error(f"Campaign {campaign.id} script has no start node — hanging up {uuid}")
            await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
            return

        await _play_ivr_node(uuid, start_node.id, session)


# ─── CHANNEL_EXECUTE_COMPLETE ─────────────────────────────────────────────────

@_consumer.handle("CHANNEL_EXECUTE_COMPLETE")
async def on_execute_complete(event):
    """Intercepts play_and_get_digits completion and routes based on pressed digit."""
    if event.get("Application") != "play_and_get_digits":
        return

    uuid          = event.get("Unique-ID")
    digit         = event.get("variable_digit_rx")
    node_id_str   = event.get("variable_current_ivr_node_id")
    campaign_id   = event.get("variable_campaign_id")
    contact_phone = event.get("variable_contact_phone")
    contact_id    = event.get("variable_contact_id")

    if not node_id_str or not digit:
        logger.info(f"No input received on {uuid} — hanging up (timeout/no-press)")
        await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
        return

    try:
        node_id = UUID(node_id_str)
    except Exception:
        return

    logger.info(f"IVR digit '{digit}' on {uuid} (node {node_id})")

    async with AsyncSessionLocal() as session:
        # Load node with routes + their response audio
        result = await session.execute(
            select(IvrNode)
            .options(selectinload(IvrNode.routes).selectinload(IvrRoute.response_audio))
            .where(IvrNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if not node:
            return

        matched_route = next(
            (r for r in node.routes if r.key_pressed == digit), None
        )
        if not matched_route:
            logger.warning(f"Digit '{digit}' matched regex but no route found on node {node_id}")
            await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
            return

        # Optional response audio to play before the action
        prefix = ""
        if matched_route.response_audio and matched_route.response_audio.file_path:
            prefix = f"playback:{matched_route.response_audio.file_path},"

        action = matched_route.action_type

        # ── TRANSFER ──────────────────────────────────────────────────────
        if action == IvrActionType.TRANSFER:
            logger.info(f"Bridging {uuid} to mod_callcenter internal_sales_queue")
            
            # Fire an event so the Dashboard knows the transfer happened
            if campaign_id:
                try:
                    camp = await session.get(Campaign, UUID(campaign_id))
                    if camp:
                        camp.transferred_count += 1
                        await session.commit()
                except Exception as e:
                    logger.error(f"Transfer counter increment failed: {e}")

            # Send straight to FreeSWITCH mod_callcenter natively
            bridge = "callcenter:internal_sales_queue"
            cmd = f"uuid_transfer {uuid} inline '{prefix}{bridge}'"
            await esl_manager.bgapi(cmd)

        # ── HANGUP ────────────────────────────────────────────────────────
        elif action == IvrActionType.HANGUP:
            logger.info(f"HANGUP route triggered for {uuid}")
            ext = f"'{prefix}hangup:NORMAL_CLEARING'" if prefix else "hangup:NORMAL_CLEARING"
            await esl_manager.bgapi(f"uuid_transfer {uuid} inline {ext}")

        # ── GO_TO_NODE ────────────────────────────────────────────────────
        elif action == IvrActionType.GO_TO_NODE:
            if not matched_route.target_node_id:
                logger.warning(f"GO_TO_NODE route has no target_node_id on {uuid}")
                await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
                return

            logger.info(f"Routing {uuid} → Node {matched_route.target_node_id}")
            if prefix:
                # Play the transition audio synchronously first, then move to node
                await esl_manager.api(
                    f"uuid_execute {uuid} playback "
                    f"{matched_route.response_audio.file_path}"
                )
            await _play_ivr_node(uuid, matched_route.target_node_id, session)


# ─── EventHandler wrapper ─────────────────────────────────────────────────────

class EventHandler:
    """Thin wrapper kept for backward-compat with main.py startup calls."""
    async def start(self):
        await esl_manager.start()
        logger.info("ESL Call Handlers & IVR Engine initialized")


event_handler = EventHandler()
