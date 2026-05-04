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
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Industry-standard retryable SIP hangup causes ───────────────────────────
# Only these causes justify a retry — everything else is a permanent failure
# and should NOT be retried (saves SIP minutes and respects carrier limits).
RETRYABLE_SIP_CAUSES = frozenset({
    'NO_USER_RESPONSE',            # Ring timeout — network reachable but no pickup
    'USER_BUSY',                   # Busy signal — temporary unavailability
    'NO_ANSWER',                   # Confirmed ring, no answer
    'RECOVERY_ON_TIMER_EXPIRE',    # Carrier-side timeout — transient
    'NORMAL_TEMPORARY_FAILURE',    # Carrier transient error (503)
    'DESTINATION_OUT_OF_ORDER',    # Temporary network issue
    'ORIGINATOR_CANCEL',           # Our side cancelled (e.g. campaign paused mid-ring)
})

# ── Handler registration ──────────────────────────────────────────────────────
# Uses esl_manager.register_handler() instead of @consumer.handle() decorators
# so that handlers persist across ESL Consumer reconnects.
# ──────────────────────────────────────────────────────────────────────────────

#DEBUG
async def on_dtmf_debug(event):
    logger.warning(
        f"[DTMF DEBUG] uuid={event.get('Unique-ID')} "
        f"digit={event.get('DTMF-Digit')} "
        f"source={event.get('DTMF-Source')} "
        f"duration={event.get('DTMF-Duration')}"
    )
esl_manager.register_handler("DTMF", on_dtmf_debug)


async def log_test_trace(event: dict, tag: str, detail: str):
    if event.get("variable_is_test_call") == "true":
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tag": tag,
                "detail": detail
            }
            await publish_event("test_logs", json.dumps(payload))
        except Exception as e:
            logger.error(f"Failed to push test log: {e}")


# ─── CHANNEL_ANSWER ───────────────────────────────────────────────────────────

async def on_channel_answer(event):
    campaign_id = event.get("variable_campaign_id")
    if not campaign_id:
        return

    uuid = event.get("Unique-ID")
    logger.info(f"Target Answered: {uuid} | Campaign: {campaign_id}")
    
    await log_test_trace(event, "NETWORK", "Call Answered. Evaluative Handlers engaged.")

    async with AsyncSessionLocal() as db:
        try:
            camp = await db.get(Campaign, UUID(campaign_id))
            if camp:
                camp.answered_count += 1
                await db.commit()
                if camp.enable_amd:
                    logger.info(f"Triggering 3-layer AMD orchestrator on {uuid}")
                    await log_test_trace(event, "AMD", "Triggering 3-layer AMD orchestration (mod_amd + avmd + whisper)...")
                    # The Lua orchestrator handles all 3 layers internally:
                    #   Layer 1: mod_amd (heuristic)
                    #   Layer 2: Whisper sidecar (AI, only if ambiguous)
                    #   Layer 3: mod_avmd (beep detection, parallel)
                    # Results arrive via amd::result CUSTOM event
                    await esl_manager.execute(uuid, "lua", "amd_orchestrator.lua")
                else:
                    await log_test_trace(event, "IVR", "AMD bypassed. Commencing start node playback.")
                    is_test = event.get("variable_is_test_call") == "true"
                    await _start_human_playlist(uuid, camp, is_test=is_test)
        except Exception as e:
            logger.error(f"on_channel_answer error: {e}", exc_info=True)
esl_manager.register_handler("CHANNEL_ANSWER", on_channel_answer)


# ─── CUSTOM EVENTS (AMD + Agent Registration) ────────────────────────────────

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

    # -- AMD Result (from amd_orchestrator.lua) --
    if subclass == "amd::result":
        await _handle_amd_result(event)
        return

    # -- Whisper Request (from amd_orchestrator.lua, Layer 2 fallback) --
    if subclass == "amd::whisper_request":
        await _handle_whisper_request(event)
        return

    # -- AVMD Beep Detection (from mod_avmd, Layer 3) --
    if subclass == "avmd::beep":
        await _handle_avmd_beep(event)
        return
esl_manager.register_handler("CUSTOM", on_custom_event)


async def _handle_amd_result(event):
    """
    Process the AMD classification result from amd_orchestrator.lua.
    
    TELEMETRY ONLY — Lua handles all call control (hangup/continue) inline.
    
    By the time this event fires:
      - HUMAN results: Lua kept call alive → we start IVR playback here
      - MACHINE + Mode A/C: Lua already executed session:hangup() → call is dead
      - MACHINE + Mode B: Lua kept avmd running → we wait for avmd::beep
      - UNKNOWN + Mode A/B: Lua already executed session:hangup() → call is dead
      - UNKNOWN + Mode C: Lua overrode result to "human" → we start IVR
    
    We NEVER call uuid_kill here. All hangups are synchronous in Lua.
    """
    uuid = event.get("Unique-ID")
    amd_result = event.get("variable_amd_result")
    amd_layer = event.get("variable_amd_layer", "unknown")
    amd_confidence = event.get("variable_amd_confidence", "0.0")
    amd_decision_ms = event.get("variable_amd_decision_ms", "0")
    campaign_id = event.get("variable_campaign_id")
    campaign_mode = event.get("variable_campaign_mode", "A")

    if not campaign_id:
        logger.warning(f"amd::result event missing campaign_id natively. Event keys: {list(event.keys())}")
        return

    logger.info(
        f"AMD Result on {uuid}: {amd_result} "
        f"(layer={amd_layer}, conf={amd_confidence}, "
        f"elapsed={amd_decision_ms}ms, mode={campaign_mode})"
    )
    await log_test_trace(
        event, "AMD",
        f"3-Layer Result: {amd_result} via {amd_layer} "
        f"(confidence={amd_confidence}, {amd_decision_ms}ms)"
    )

    async with AsyncSessionLocal() as db:
        try:
            camp = await db.get(Campaign, UUID(campaign_id))
            if not camp:
                return

            if amd_result == "human":
                # Telemetry only — IVR is triggered by CHANNEL_EXECUTE_COMPLETE
                # for the Lua app, guaranteeing the channel thread is free.
                await log_test_trace(event, "IVR", "Human confirmed by AMD. IVR starts on Lua completion.")

            elif amd_result == "machine":
                camp.voicemail_count += 1
                await db.commit()
                
                if campaign_mode == "B":
                    # Mode B: Lua keeps avmd running — beep handler will play VM drop
                    logger.info(f"AMD MACHINE on {uuid} + Mode B — waiting for avmd::beep")
                    await log_test_trace(event, "AMD", "Machine detected (Mode B). Waiting for beep to drop voicemail.")
                else:
                    # Mode A/C: Lua already hung up the call via session:hangup()
                    logger.info(f"AMD MACHINE on {uuid} + Mode {campaign_mode} — Lua already hung up")
                    await log_test_trace(event, "AMD", f"Machine detected (Mode {campaign_mode}). Call terminated by Lua.")

            elif amd_result == "unknown":
                # Mode C treats unknown as human (done in Lua, result overridden to 'human')
                # This branch only fires for Mode A/B where Lua already hung up
                logger.info(f"AMD UNKNOWN on {uuid} + Mode {campaign_mode} — Lua already hung up")
                await log_test_trace(event, "AMD", f"AMD timeout/unknown (Mode {campaign_mode}). Call terminated by Lua.")

        except Exception as e:
            logger.error(f"_handle_amd_result error: {e}", exc_info=True)


async def _handle_whisper_request(event):
    """
    Handle Layer 2 Whisper AMD request from amd_orchestrator.lua.
    
    The Lua script recorded a short audio file to the shared /audio volume
    and fired this event requesting the Python backend to stream it to the
    Whisper sidecar and write the result back as channel variables.
    
    Path translation:
      FS container sees: /audio/amd_{uuid}.wav
      Backend (local dev) sees: ./data/audio/amd_{uuid}.wav
      Backend (Docker prod) sees: /audio/amd_{uuid}.wav
    We use settings.AUDIO_DIR to construct the correct local path.
    """
    uuid = event.get("Unique-ID")
    whisper_file = event.get("variable_amd_whisper_file")
    campaign_id = event.get("variable_campaign_id")

    if not uuid or not whisper_file:
        return

    # Translate FS container path → backend-local path
    # FS always writes to /audio/<filename>, we replace the /audio prefix
    # with the configured AUDIO_DIR (./data/audio in dev, /audio in Docker)
    import os
    filename = os.path.basename(whisper_file)
    local_path = os.path.join(settings.AUDIO_DIR, filename)

    logger.info(f"Whisper AMD request for {uuid}: FS path={whisper_file}, local path={local_path}")

    try:
        import websockets
        import soundfile as sf
        import numpy as np

        # Read the recorded audio file from the shared volume
        audio_data, sample_rate = sf.read(local_path, dtype='int16')
        
        # Resample to 16kHz mono if needed (numpy-only, no scipy required)
        if sample_rate != 16000:
            # Linear interpolation resampling — sufficient for speech AMD
            num_samples = int(len(audio_data) * 16000 / sample_rate)
            indices = np.linspace(0, len(audio_data) - 1, num_samples)
            audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data.astype(np.float64)).astype(np.int16)
        
        # Ensure mono
        if len(audio_data.shape) > 1:
            audio_data = audio_data[:, 0]

        # Connect to Whisper sidecar WebSocket
        ws_url = settings.WHISPER_AMD_WS_URL
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            # Send audio in chunks (640 bytes = 20ms at 16kHz PCM16)
            chunk_size = 640
            audio_bytes = audio_data.tobytes()
            
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i + chunk_size]
                await ws.send(chunk)
            
            # Request final decision
            await ws.send(json.dumps({"type": "flush"}))
            
            # Wait for final response
            response_text = await asyncio.wait_for(ws.recv(), timeout=10.0)
            result = json.loads(response_text)
            
            # If we got an early decision first, read again for final
            if result.get("type") == "early":
                try:
                    response_text = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    result = json.loads(response_text)
                except Exception:
                    pass  # Use early decision if final doesn't arrive
            
            # Write results back to the channel as variables
            label = result.get("label", "unknown")
            confidence = str(result.get("confidence", 0.0))
            transcript = result.get("transcript", "")
            
            await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_result {label}")
            await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_confidence {confidence}")
            # Transcript may contain spaces — replace for channel var safety
            if transcript:
                safe_transcript = transcript[:200].replace(" ", "_")
                await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_transcript {safe_transcript}")
            
            logger.info(
                f"Whisper result for {uuid}: {label} "
                f"(conf={confidence}, transcript='{transcript[:60]}')"
            )

    except FileNotFoundError:
        logger.error(f"Whisper audio file not found: {local_path}")
        await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_result unknown")
        await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_confidence 0.0")
    except Exception as e:
        logger.error(f"Whisper AMD processing failed for {uuid}: {e}", exc_info=True)
        # Set fallback so Lua doesn't wait forever
        await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_result unknown")
        await esl_manager.api(f"uuid_setvar {uuid} amd_whisper_confidence 0.0")
    finally:
        # Clean up the temporary recording file
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.debug(f"Cleaned up AMD recording: {local_path}")
        except OSError as e:
            logger.warning(f"Failed to clean up AMD recording {local_path}: {e}")


async def _handle_avmd_beep(event):
    """
    Handle beep detection from mod_avmd (Layer 3).
    
    This only fires when mod_avmd detects a 1000Hz beep tone.
    Action depends on campaign_mode:
      - Mode B + MACHINE: Play VM drop audio, then hangup
      - All other cases: Ignore (avmd should have been stopped by Lua)
    """
    uuid = event.get("Unique-ID")
    campaign_id = event.get("variable_campaign_id")
    campaign_mode = event.get("variable_campaign_mode", "A")
    vm_drop_audio_id = event.get("variable_vm_drop_audio_id")
    amd_result = event.get("variable_amd_result", "")

    if not uuid or not campaign_id:
        return

    logger.info(f"AVMD beep detected on {uuid} (mode={campaign_mode}, amd_result={amd_result})")

    # Only act on Mode B + machine detection
    if campaign_mode != "B" or amd_result != "machine":
        logger.info(f"Beep on {uuid} ignored — mode={campaign_mode}, result={amd_result}")
        # Stop avmd to free CPU
        await esl_manager.execute(uuid, "avmd", "stop")
        return

    # Mode B: Play VM drop audio then hangup
    async with AsyncSessionLocal() as db:
        try:
            if vm_drop_audio_id:
                audio_row = await db.get(AudioFile, UUID(vm_drop_audio_id))
                if audio_row and audio_row.file_path:
                    import os
                    fs_path = f"/audio/{os.path.basename(audio_row.file_path)}"
                    logger.info(f"Playing VM drop for {uuid}: {fs_path}")
                    await log_test_trace(
                        event, "AMD",
                        f"Beep detected! Playing voicemail drop: {audio_row.name}"
                    )
                    # Stop avmd first (save CPU), then play + hangup
                    await esl_manager.execute(uuid, "avmd", "stop")
                    await esl_manager.bgapi(
                        f"uuid_transfer {uuid} 'playback:{fs_path},hangup:NORMAL_CLEARING' inline"
                    )
                    return

            # No VM drop audio configured — just hangup
            logger.info(f"No VM drop audio for {uuid} — hanging up")
            await esl_manager.execute(uuid, "avmd", "stop")
            await esl_manager.api(f"uuid_kill {uuid}")

        except Exception as e:
            logger.error(f"_handle_avmd_beep error: {e}", exc_info=True)


# ─── CHANNEL_BRIDGE (MOD_CALLCENTER SCREEN POP) ───────────────────────────────

async def on_channel_bridge(event):
    cc_agent = event.get("variable_cc_agent")
    if not cc_agent:
        return
        
    caller_num = event.get("variable_contact_phone") or event.get("Caller-Destination-Number", "Unknown")
    campaign_id = event.get("variable_campaign_id", "Unknown")
    uuid = event.get("Unique-ID", "")
    
    logger.info(f"mod_callcenter bridged call to agent {cc_agent} (Caller: {caller_num})")
    
    async with AsyncSessionLocal() as db:
        try:
            # Look up the agent based on their extension/sip which is stored in phone_or_sip
            result = await db.execute(select(Agent).where(Agent.phone_or_sip == cc_agent))
            agent = result.scalar_one_or_none()
            
            agent_name = cc_agent  # fallback to extension
            agent_ext = cc_agent
            if agent:
                agent_name = agent.name or cc_agent
                agent_ext = agent.phone_or_sip or cc_agent
                
                # Screen pop for the agent's softphone UI
                payload = {
                    "event": "AGENT_RINGING",
                    "agent_id": str(agent.id),
                    "caller_number": caller_num,
                    "campaign_id": campaign_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await publish_event(f"agent_events:{agent.id}", json.dumps(payload))
                logger.info(f"Published screen pop for Agent {agent.id}")
            
            # ── Publish bridge info to live transfer dashboard ────────────
            # This updates the transfer card from "Bridging" to show the
            # agent name/extension who actually picked up the call.
            bridge_payload = {
                "event": "TRANSFER_BRIDGED",
                "uuid": uuid,
                "campaign_id": campaign_id,
                "phone_number": caller_num,
                "agent_name": agent_name,
                "agent_extension": agent_ext,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await publish_event("dashboard_events", json.dumps(bridge_payload))
            
        except Exception as e:
            logger.error(f"Failed to lookup agent for screen pop: {e}", exc_info=True)
esl_manager.register_handler("CHANNEL_BRIDGE", on_channel_bridge)


# ─── CHANNEL_HANGUP (Future Cleanup) ───────────────────────────────────────────────────────

async def on_channel_hangup(event):
    """Immediately cancel all pending execute futures for this channel.

    Fires BEFORE CHANNEL_HANGUP_COMPLETE.  Cancelling futures here prevents
    leaked coroutines when calls drop mid-AMD (up to 10s per call at scale).
    Without this, each dropped call leaks a Future that never resolves.
    """
    uuid = event.get("Unique-ID")
    if uuid:
        esl_manager.cancel_pending_for_uuid(uuid)
esl_manager.register_handler("CHANNEL_HANGUP", on_channel_hangup)


# ─── CHANNEL_HANGUP_COMPLETE ──────────────────────────────────────────────────────────────────

async def on_hangup(event):
    queue_id    = event.get("variable_dial_queue_id")
    campaign_id = event.get("variable_campaign_id")
    # Capture phone from the ESL event BEFORE any try/except
    # so the variable is available in the publish block regardless of exceptions.
    phone_number = (
        event.get("variable_contact_phone")
        or event.get("Caller-Destination-Number")
        or "Unknown"
    )

    cause = event.get("variable_hangup_cause", "UNKNOWN")
    logger.info(f"Hangup uuid={event.get('Unique-ID')} cause={cause} queue_id={queue_id}")

    # Publish disconnect trace BEFORE the queue_id guard so test calls
    # (which have no dial_queue_id) still get the "Call Disconnected" message.
    await log_test_trace(event, "NETWORK", f"Call Disconnected. Cause: {cause}")

    if not queue_id:
        return

    # Release capacity to the system instantaneously (async + floor clamp)
    if campaign_id:
        current_val = await redis_client.decr(f"campaign_active:{campaign_id}")
        if current_val is not None and int(current_val) < 0:
            await redis_client.set(f"campaign_active:{campaign_id}", 0)

    async with AsyncSessionLocal() as db:
        try:
            q_item = await db.get(DialQueue, UUID(queue_id))
            camp = await db.get(Campaign, UUID(campaign_id)) if campaign_id else None

            # ── Update campaign counters ──────────────────────────────────
            # dialed_count is incremented at originate dispatch time (in the
            # dialer) for real-time visibility. Here we only track failures.
            if camp:
                # Determine if this was a failure (non-normal, non-answer disposition)
                is_answered = cause == 'NORMAL_CLEARING'
                is_retryable = cause in RETRYABLE_SIP_CAUSES
                is_permanent_failure = not is_answered and not is_retryable

                if is_permanent_failure:
                    camp.failed_count += 1

            # ── Retry or remove from queue ────────────────────────────────
            if q_item and camp:
                if (
                    cause in RETRYABLE_SIP_CAUSES
                    and q_item.retry_count < camp.retry_attempts
                ):
                    logger.info(
                        f"Rescheduling {q_item.phone_number} "
                        f"(attempt {q_item.retry_count + 1}/{camp.retry_attempts}, "
                        f"cause={cause})"
                    )
                    q_item.retry_count += 1
                    q_item.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        minutes=camp.retry_delay_min
                    )
                    q_item.locked_by = None
                    q_item.locked_at = None
                else:
                    await db.delete(q_item)
            elif q_item:
                # No campaign ref — just remove the orphan queue item
                await db.delete(q_item)

            # ── Insert Call Details Record with AMD telemetry ─────────────
            duration = int(float(event.get("variable_billsec", 0)))
            amd_result = event.get("variable_amd_result", "UNKNOWN")
            contact_id = event.get("variable_contact_id")

            # AMD telemetry from amd_orchestrator.lua channel variables
            amd_layer = event.get("variable_amd_layer")
            amd_decision_ms_raw = event.get("variable_amd_decision_ms")
            amd_decision_ms = int(float(amd_decision_ms_raw)) if amd_decision_ms_raw else None
            amd_confidence_raw = event.get("variable_amd_confidence")
            amd_confidence = float(amd_confidence_raw) if amd_confidence_raw else None
            amd_transcript = event.get("variable_amd_transcript")
            # Restore spaces from underscore encoding (Lua channel var safety)
            if amd_transcript:
                amd_transcript = amd_transcript.replace("_", " ")

            call_log = CallLog(
                campaign_id=UUID(campaign_id) if campaign_id else None,
                contact_id=UUID(contact_id) if contact_id else None,
                phone_number=phone_number,
                duration=duration,
                hangup_cause=cause,
                amd_result=amd_result,
                amd_layer=amd_layer,
                amd_decision_ms=amd_decision_ms,
                amd_confidence=amd_confidence,
                amd_transcript=amd_transcript,
            )
            db.add(call_log)
            await db.commit()

        except Exception as e:
            logger.error(f"on_hangup db error: {e}", exc_info=True)

        # Always publish dashboard event — even if db ops failed
        try:
            # Use campaign name from the DB object fetched earlier in this handler.
            # NOTE: Do NOT re-import redis_client here — a local import shadows
            # the module-level import and causes UnboundLocalError on line 455,
            # crashing the entire hangup pipeline.
            camp_name = camp.name if camp else "Unknown Campaign"

            payload = {
                "event":        "CALL_ENDED",
                "uuid":         event.get("Unique-ID"),
                "phone_number": phone_number,
                "cause":        cause,
                "campaign_id":  campaign_id,
                "campaign_name": camp_name,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
            }
            await publish_event("dashboard_events", json.dumps(payload))
        except Exception as e:
            logger.error(f"on_hangup publish error: {e}", exc_info=True)
esl_manager.register_handler("CHANNEL_HANGUP_COMPLETE", on_hangup)


# ─── IVR ENGINE ───────────────────────────────────────────────────────────────

async def _play_ivr_node(uuid: str, node_id: UUID, session, is_test: bool = False) -> None:
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

    import os
    fs_prompt_path = f"/audio/{os.path.basename(prompt_path)}"



    # ── Carrier-Immune DTMF Normalization ──────────────────────────────────
    # 1. Engage SpanDSP in-band audio detector for carrier-immune DTMF.
    #    spandsp_start_dtmf uses the industrial SpanDSP Goertzel algorithm
    #    which reliably detects DTMF even through codec transcoding, SBC
    #    mangling, and carriers that strip RFC2833 telephone-event.
    #    CRITICAL: Do NOT also enable start_dtmf — running two detectors
    #    simultaneously causes double-detection feedback loops.
    logger.info(f"Executing spandsp_start_dtmf on {uuid}...")
    spandsp_res = await esl_manager.execute(uuid, "spandsp_start_dtmf", "")
    logger.info(f"Response from spandsp_start_dtmf: {spandsp_res}")
    
    # 2. Flush the channel buffer to instantly destroy lingering inputs from previous menus
    await esl_manager.execute(uuid, "flush_dtmf", "")

    # play_and_get_digits args: min max tries timeout terminators file invalid_file var_name regexp
    app_arg = f"1 1 3 5000 # {fs_prompt_path} silence_stream://250 digit_rx {regex}"
    
    logger.info(f"IVR play_and_get_digits on {uuid} | node={node.name!r} | regex={regex}")
    logger.info(f"ESL sendmsg => execute play_and_get_digits {app_arg}")
    
    if is_test:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "tag": "IVR", "detail": f"Prompting Node: {node.name} (Awaiting Input...)"}
        await publish_event("test_logs", json.dumps(payload))
        
    result = await esl_manager.execute(uuid, "play_and_get_digits", app_arg)
    logger.info(f"ESL sendmsg response => {result}")


async def _start_human_playlist(uuid: str, campaign: Campaign, is_test: bool = False) -> None:
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

        await _play_ivr_node(uuid, start_node.id, session, is_test=is_test)


# ─── CHANNEL_EXECUTE_COMPLETE ─────────────────────────────────────────────────

async def on_execute_complete(event):
    """
    Central execute-complete dispatcher.

    Handles:
      1. Resolving pending execute_and_wait() futures via Application-UUID
      2. AMD Lua script completion → starts IVR for human-classified calls
      3. play_and_get_digits completion → routes IVR based on pressed digit
    """
    uuid = event.get("Unique-ID")
    application = event.get("Application")

    # ── Resolve pending execute_and_wait futures (non-blocking) ───────────────
    app_uuid = event.get("Application-UUID")
    if app_uuid and uuid:
        esl_manager.resolve_execute(app_uuid, uuid, event)

    # ── AMD Lua script completed → channel thread is now free ───────────────
    # The Lua script sets channel variables BEFORE firing amd::result and
    # BEFORE returning.  By the time CHANNEL_EXECUTE_COMPLETE fires for
    # the "lua" app, the channel thread is idle and safe to receive new
    # sendmsg commands (play_and_get_digits for IVR).
    if application == "lua":
        amd_result = event.get("variable_amd_result")
        campaign_id = event.get("variable_campaign_id")
        if amd_result == "human" and campaign_id and uuid:
            logger.info(f"Lua AMD complete on {uuid} — human detected, starting IVR")
            await log_test_trace(
                event, "IVR",
                "AMD Lua returned. Channel free — starting IVR playback."
            )
            try:
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, UUID(campaign_id))
                    if camp:
                        is_test = event.get("variable_is_test_call") == "true"
                        await _start_human_playlist(uuid, camp, is_test=is_test)
            except Exception as e:
                logger.error(f"IVR start after AMD on {uuid}: {e}", exc_info=True)
        return

    # ── IVR play_and_get_digits completion ───────────────────────────────────
    if application != "play_and_get_digits":
        return

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
    await log_test_trace(event, "IVR", f"User processed digit '{digit}'")
    
    # CRITICAL: Always shut off the heavy in-band interceptor before moving to 
    # the next phase. If the next phase is a TRANSFER to an agent, leaving this 
    # running will permanently intercept/mangle bridge audio. If the next phase 
    # is another PROMPT, the start command will be safely re-issued.
    await esl_manager.execute(uuid, "spandsp_stop_dtmf", "")

    async with AsyncSessionLocal() as session:
        # Load node with routes + their response audio
        result = await session.execute(
            select(IvrNode)
            .options(
                selectinload(IvrNode.routes).selectinload(IvrRoute.response_audio),
                selectinload(IvrNode.routes).selectinload(IvrRoute.target_node),
            )
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

        target_node = matched_route.target_node
        if not target_node:
            logger.warning(f"Digit '{digit}' matched but target node is missing for {uuid}")
            await esl_manager.bgapi(f"uuid_kill {uuid} NORMAL_CLEARING")
            return

        # Optional response audio defined directly on the Terminal Node itself
        prefix = ""
        if target_node.node_type in ["TRANSFER", "HANGUP", "DNC"]:
            if target_node.prompt_audio_id:
                audio_row = await session.execute(select(AudioFile).where(AudioFile.id == target_node.prompt_audio_id))
                audio_row = audio_row.scalar_one_or_none()
                if audio_row and audio_row.file_path:
                    import os
                    fs_path = f"/audio/{os.path.basename(audio_row.file_path)}"
                    prefix = f"playback:{fs_path},"
            elif target_node.tts_text:
                try:
                    voice = target_node.tts_voice or "af_heart"
                    prompt_path = await synthesize_node_prompt(str(target_node.id), target_node.tts_text, voice)
                    if prompt_path:
                        import os
                        fs_path = f"/audio/{os.path.basename(prompt_path)}"
                        prefix = f"playback:{fs_path},"
                except Exception as e:
                    logger.error(f"TTS synthesis failed for terminal node {target_node.id}: {e}")

        action = target_node.node_type

        # ── TRANSFER ──────────────────────────────────────────────────────
        if action == "TRANSFER": # or IvrNodeType.TRANSFER
            # Route to campaign-specific queue if available, else global fallback
            from app.engine.queue_manager import get_queue_name_for_campaign
            queue_name = get_queue_name_for_campaign(campaign_id)
            logger.info(f"Bridging {uuid} to mod_callcenter queue '{queue_name}'")
            await log_test_trace(event, "ROUTING", f"Action TRANSFER triggered. Bridging to queue '{queue_name}'.")
            
            caller_number = event.get("Caller-Caller-ID-Number", "unknown")
            
            if campaign_id:
                try:
                    camp = await session.get(Campaign, UUID(campaign_id))
                    if camp:
                        camp.transferred_count += 1
                        await session.commit()
                except Exception as e:
                    logger.error(f"Transfer counter increment failed: {e}")
                
                # Publish transfer event for live dashboard
                try:
                    import json as _json
                    await publish_event("dashboard_events", _json.dumps({
                        "event": "TRANSFER_INITIATED",
                        "campaign_id": campaign_id,
                        "phone_number": caller_number,
                        "queue": queue_name,
                        "uuid": uuid,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                except Exception:
                    pass  # Dashboard event is non-critical

            bridge = f"callcenter:{queue_name}"
            dest = f"{prefix}{bridge}"
            cmd = f"uuid_transfer {uuid} '{dest}' inline"
            await esl_manager.bgapi(cmd)

        # ── HANGUP ────────────────────────────────────────────────────────
        elif action == "HANGUP":
            logger.info(f"HANGUP node triggered for {uuid}")
            await log_test_trace(event, "ACTION", "Script specified direct HANGUP. Terminating.")
            dest = f"'{prefix}hangup:NORMAL_CLEARING'" if prefix else "'hangup:NORMAL_CLEARING'"
            await esl_manager.bgapi(f"uuid_transfer {uuid} {dest} inline")

        # ── DNC ───────────────────────────────────────────────────────────
        elif action == "DNC":
            logger.info(f"DNC node triggered for {uuid}. Marking contact {contact_id} as DNC.")
            if contact_id:
                try:
                    contact = await session.get(Contact, UUID(contact_id))
                    if contact:
                        extra = dict(contact.extra) if contact.extra else {}
                        extra['dnc'] = True
                        contact.extra = extra
                        await session.commit()
                except Exception as e:
                    logger.error(f"Failed to update contact DNC status: {e}", exc_info=True)
            
            dest = f"'{prefix}hangup:NORMAL_CLEARING'" if prefix else "'hangup:NORMAL_CLEARING'"
            await esl_manager.bgapi(f"uuid_transfer {uuid} {dest} inline")

        # ── PROMPT ────────────────────────────────────────────────────
        elif action == "PROMPT":
            logger.info(f"Routing {uuid} → Node {matched_route.target_node_id}")
            await log_test_trace(event, "ROUTING", f"Navigating to Linked Node ID: {matched_route.target_node_id}")
            if prefix:
                import os
                fs_action_path = f"/audio/{os.path.basename(matched_route.response_audio.file_path)}"
                await esl_manager.execute(uuid, "playback", fs_action_path)
            
            is_test = event.get("variable_is_test_call") == "true"
            await _play_ivr_node(uuid, matched_route.target_node_id, session, is_test=is_test)

esl_manager.register_handler("CHANNEL_EXECUTE_COMPLETE", on_execute_complete)


# ─── EventHandler wrapper ─────────────────────────────────────────────────────

class EventHandler:
    """Thin wrapper kept for backward-compat with main.py startup calls."""
    async def start(self):
        await esl_manager.start()
        logger.info("ESL Call Handlers & IVR Engine initialized")


event_handler = EventHandler()
