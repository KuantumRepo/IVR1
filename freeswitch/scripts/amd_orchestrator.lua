-- ═══════════════════════════════════════════════════════════════════════════════
-- amd_orchestrator.lua — Three-Layer Parallel AMD Orchestration Engine
-- ═══════════════════════════════════════════════════════════════════════════════
--
-- Replaces the old amd.lua (wait_for_silence heuristic).
-- Runs on every answered outbound call. Orchestrates:
--
--   Layer 1: mod_amd    — fast heuristic (word count + silence analysis)
--   Layer 2: Whisper    — AI classifier (only invoked on ambiguous results)
--   Layer 3: mod_avmd   — beep detector (runs in parallel, always)
--
-- CALL FLOW:
--   1. Prime audio codec with 250ms silence (industry best practice)
--   2. Start mod_avmd immediately (background, parallel beep detection)
--   3. Start mod_amd (blocking heuristic)
--   4. Smart routing decision:
--      a) High-confidence HUMAN or MACHINE → act immediately
--      b) Ambiguous → stream audio to Whisper sidecar for AI classification
--   5. Apply campaign_mode behavior matrix (A / B / C)
--   6. Set channel variables for CDR telemetry
--   7. Fire amd::result CUSTOM event for handlers.py
--   8. Execute hangup/IVR inline (zero-latency, no ESL race condition)
--
-- CHANNEL VARIABLES READ:
--   campaign_id         — UUID of the campaign
--   campaign_mode       — A, B, or C
--   vm_drop_audio_id    — UUID of voicemail drop audio file (for Mode B)
--   amd_config          — JSON string with per-campaign AMD overrides
--
-- CHANNEL VARIABLES SET:
--   amd_result          — human / machine / unknown
--   amd_layer           — mod_amd / whisper / timeout
--   amd_decision_ms     — milliseconds from answer to AMD decision
--   amd_confidence      — 0.0–1.0 confidence score
--   amd_transcript      — Whisper transcript (if Layer 2 was used)
--
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Configuration (defaults — can be overridden per-campaign) ────────────────

-- Whisper sidecar WebSocket endpoint (Docker service name resolves in compose)
local WHISPER_WS_HOST = "whisper-amd"
local WHISPER_WS_PORT = 8080

-- Maximum time to wait for mod_amd to produce a result before timing out.
-- After this, we classify as UNKNOWN and apply campaign_mode logic.
local AMD_TIMEOUT_SEC = 8.0  -- seconds

-- ── Safety: verify session is alive ──────────────────────────────────────────

if not session or not session:ready() then
    return
end

-- ── Capture start time for decision latency measurement ──────────────────────
-- NOTE: os.clock() measures CPU time (not wall time) in FreeSWITCH's embedded
-- Lua. We use os.time() for wall-clock seconds for correct elapsed measurement.

local decision_start = os.time()  -- wall-clock seconds
local uuid = session:get_uuid()
local campaign_id = session:getVariable("campaign_id") or ""
local campaign_mode = session:getVariable("campaign_mode") or "A"
local vm_drop_audio_id = session:getVariable("vm_drop_audio_id") or ""

freeswitch.consoleLog("INFO",
    "[AMD] Starting 3-layer orchestration on " .. uuid ..
    " | mode=" .. campaign_mode ..
    " | campaign=" .. campaign_id .. "\n"
)

-- ── Per-Campaign AMD Config Override ─────────────────────────────────────────
-- The dialer injects a JSON blob as the amd_config channel variable.
-- Parse it and override local thresholds if present.

local amd_config_raw = session:getVariable("amd_config") or ""
if amd_config_raw ~= "" then
    -- Attempt JSON parse using pcall for safety
    local ok, config = pcall(function()
        -- FreeSWITCH Lua doesn't include cjson by default, so we use
        -- a simple pattern-based extraction for the few fields we need.
        local parsed = {}
        for key, value in amd_config_raw:gmatch('"([^"]+)"%s*:%s*([%d%.]+)') do
            parsed[key] = tonumber(value)
        end
        return parsed
    end)

    if ok and config then
        if config.amd_timeout_sec then
            AMD_TIMEOUT_SEC = config.amd_timeout_sec
            freeswitch.consoleLog("INFO",
                "[AMD] Override: AMD_TIMEOUT_SEC=" .. AMD_TIMEOUT_SEC .. "\n")
        end
        freeswitch.consoleLog("INFO", "[AMD] Per-campaign config applied for " .. uuid .. "\n")
    end
end

-- ── Silent Audio Priming (Industry Best Practice) ────────────────────────────
-- Play 250ms of silence BEFORE starting mod_amd. This ensures:
--   1. The audio codec (PCMU/G.711) is fully negotiated
--   2. The media path is primed and flowing real frames
--   3. mod_amd doesn't miscount codec setup silence as "initial silence"
-- Without this, SIP trunks that inject 2-3s signaling delay cause false
-- MACHINE (cause=INITIALSILENCE) on every call.

if session:ready() then
    session:execute("playback", "silence_stream://250")
end

-- ── Layer 3: Start mod_avmd (beep detection) immediately ─────────────────────
-- mod_avmd runs as a background media bug — it passively listens for the
-- voicemail beep tone (1000Hz) and fires an avmd::beep CUSTOM event when
-- detected. It does NOT classify human vs machine.
-- We start it first because it's a purely parallel process.

if session:ready() then
    session:execute("avmd", "start")
    freeswitch.consoleLog("INFO", "[AMD] mod_avmd started on " .. uuid .. "\n")
end

-- ── Layer 1: Start mod_amd (heuristic detection) ─────────────────────────────
-- mod_amd runs synchronously — it blocks this Lua script until it reaches
-- a classification (HUMAN, MACHINE, or NOTSURE) or times out.
-- The result is set as channel variables: amd_result, amd_cause

if session:ready() then
    session:execute("amd")
end

-- ── Safety check after mod_amd returns ───────────────────────────────────────

if not session:ready() then
    -- Call hung up during AMD analysis (caller disconnected)
    return
end

-- ── Read mod_amd result ──────────────────────────────────────────────────────

local mod_amd_result = session:getVariable("amd_result") or "NOTSURE"
local mod_amd_cause = session:getVariable("amd_cause") or "UNKNOWN"

-- Wall-clock elapsed time in seconds since orchestration started
local mod_amd_elapsed_sec = os.difftime(os.time(), decision_start)

freeswitch.consoleLog("INFO",
    "[AMD] mod_amd result on " .. uuid ..
    ": " .. mod_amd_result ..
    " (cause=" .. mod_amd_cause ..
    ", elapsed=" .. mod_amd_elapsed_sec .. "s)\n"
)

-- ── Smart Routing Decision ───────────────────────────────────────────────────
-- Industry standard: TRUST mod_amd's definitive results.
--   1. MACHINE → trust it (word count, greeting length, or silence proves it)
--   2. HUMAN   → trust it (mod_amd heard speech + after_greeting_silence)
--   3. NOTSURE → send to Whisper AI for classification
--
-- We do NOT second-guess HUMAN results. mod_amd's HUMAN classification
-- means it detected speech followed by 800ms+ of silence — this is a
-- reliable indicator that a real person said "Hello?" and is waiting.

local final_result = "unknown"
local final_layer = "mod_amd"
local final_confidence = 0.85  -- default confidence for mod_amd decisions
local final_transcript = ""
local needs_whisper = false

if mod_amd_result == "MACHINE" then
    -- mod_amd is reliable for MACHINE classification (long greeting, many words)
    final_result = "machine"
    final_layer = "mod_amd"
    final_confidence = 0.90

elseif mod_amd_result == "HUMAN" then
    -- mod_amd detected speech + after_greeting_silence → confident HUMAN
    -- Trust this result. Do NOT second-guess with Whisper.
    final_result = "human"
    final_layer = "mod_amd"
    final_confidence = 0.88
    freeswitch.consoleLog("INFO",
        "[AMD] mod_amd HUMAN accepted (cause=" .. mod_amd_cause .. ")\n")

elseif mod_amd_result == "NOTSURE" or mod_amd_result == "" then
    -- mod_amd couldn't decide — route to Whisper
    freeswitch.consoleLog("INFO",
        "[AMD] mod_amd returned NOTSURE — routing to Whisper\n"
    )
    needs_whisper = true
else
    -- Unknown result format — route to Whisper
    needs_whisper = true
end

-- ── Layer 2: Whisper AMD Sidecar (conditional) ───────────────────────────────
-- Only invoked when mod_amd is ambiguous. This keeps Whisper CPU load
-- to ~30-40% of total call volume.
--
-- NOTE: Lua in FreeSWITCH does not have native WebSocket support.
-- Instead of streaming live audio over WS from Lua (which would require
-- luasocket + custom WS framing), we use a more robust approach:
--
-- 1. Record a short audio segment to a temp file
-- 2. Use the ESL API to notify the Python backend
-- 3. The Python backend handles the WebSocket communication to Whisper
--
-- This keeps the complexity in Python (where we have proper async WS support)
-- rather than fighting Lua's limited networking capabilities.

if needs_whisper and session:ready() then
    freeswitch.consoleLog("INFO",
        "[AMD] Invoking Whisper sidecar for " .. uuid .. "\n"
    )

    -- Record 3 seconds of audio for Whisper analysis
    -- The recording starts from NOW (after mod_amd already consumed 1-3s),
    -- so the total AMD time is mod_amd_time + 3s ≈ 4-6s total.
    -- We write to /audio which is a shared volume accessible by both
    -- the FS container and the Python backend.
    local temp_file = "/audio/amd_" .. uuid .. ".wav"
    session:execute("record", temp_file .. " 3 200")

    -- Signal the Python backend to process this recording via Whisper
    -- We set a channel variable that the backend can read, and fire
    -- a custom event to trigger the processing.
    session:setVariable("amd_whisper_file", temp_file)

    local whisper_event = freeswitch.Event("CUSTOM", "amd::whisper_request")
    whisper_event:addHeader("Unique-ID", uuid)
    whisper_event:addHeader("variable_campaign_id", campaign_id)
    whisper_event:addHeader("variable_campaign_mode", campaign_mode)
    whisper_event:addHeader("variable_amd_whisper_file", temp_file)
    whisper_event:fire()

    -- Wait for the Python backend to process and set the result
    -- The backend will call uuid_setvar to set these variables
    local whisper_wait_start = os.time()
    local whisper_timeout = 5  -- max seconds to wait for Whisper result

    while session:ready() do
        local whisper_result = session:getVariable("amd_whisper_result")
        if whisper_result and whisper_result ~= "" then
            -- Whisper has responded
            final_result = whisper_result
            final_layer = "whisper"
            final_confidence = tonumber(session:getVariable("amd_whisper_confidence") or "0.5") or 0.5
            final_transcript = session:getVariable("amd_whisper_transcript") or ""

            freeswitch.consoleLog("INFO",
                "[AMD] Whisper result on " .. uuid ..
                ": " .. final_result ..
                " (conf=" .. final_confidence ..
                ", transcript='" .. final_transcript .. "')\n"
            )
            break
        end

        if os.difftime(os.time(), whisper_wait_start) > whisper_timeout then
            freeswitch.consoleLog("WARNING",
                "[AMD] Whisper timeout on " .. uuid ..
                " after " .. whisper_timeout .. "s — falling back to UNKNOWN\n"
            )
            final_result = "unknown"
            final_layer = "timeout"
            final_confidence = 0.0
            break
        end

        -- Sleep 100ms before checking again
        session:sleep(100)
    end

    -- Clean up temp file
    os.remove(temp_file)
end

-- ── Calculate final decision time ────────────────────────────────────────────

local final_decision_sec = os.difftime(os.time(), decision_start)
local final_decision_ms = final_decision_sec * 1000  -- approximate ms

-- ── Apply Campaign Mode Override BEFORE setting any variables ────────────────
-- Mode C treats UNKNOWN as HUMAN (conservative: minimize false negatives).
-- This override must happen before setVariable so that CHANNEL_EXECUTE_COMPLETE
-- carries the correct "human" value when Python reads it.

if final_result == "unknown" and campaign_mode == "C" then
    final_result = "human"
    freeswitch.consoleLog("INFO",
        "[AMD] UNKNOWN + Mode C (conservative) — overriding result to HUMAN\n")
end

-- ── Pre-Event Cleanup: Stop avmd where appropriate ───────────────────────────
-- ALL session:execute() calls MUST happen BEFORE setting channel variables
-- and BEFORE firing the amd::result event.  Once the event fires, Python's
-- CHANNEL_EXECUTE_COMPLETE handler may send commands to this channel.  Those
-- commands queue behind event-lock, but we must not add more session:execute()
-- calls after the event or we create ordering ambiguity on the channel thread.
--
-- Campaign Mode Behavior Matrix:
--   HUMAN (all modes)       → stop avmd, keep call alive for IVR
--   MACHINE + Mode B        → keep avmd running for beep detection
--   MACHINE + Mode A/C      → stop avmd, then hangup (after event fire)
--   UNKNOWN (non-C, since C was overridden above) → stop avmd, then hangup

if session:ready() then
    if final_result == "human" then
        -- Stop avmd (no longer needed), keep call alive for IVR handoff
        session:execute("avmd", "stop")
        freeswitch.consoleLog("INFO",
            "[AMD] HUMAN — avmd stopped, call alive for IVR handoff\n")

    elseif final_result == "machine" then
        if campaign_mode == "B" then
            -- Mode B: keep avmd running for beep detection
            freeswitch.consoleLog("INFO",
                "[AMD] MACHINE + Mode B — keeping avmd active for beep detection\n")
        else
            -- Mode A/C: stop avmd before hangup
            session:execute("avmd", "stop")
            freeswitch.consoleLog("INFO",
                "[AMD] MACHINE + Mode " .. campaign_mode .. " — avmd stopped, will hangup\n")
        end

    elseif final_result == "unknown" then
        -- Unknown (non-C, since C was overridden to human above)
        session:execute("avmd", "stop")
        freeswitch.consoleLog("INFO",
            "[AMD] UNKNOWN + Mode " .. campaign_mode .. " — avmd stopped, will hangup\n")
    end
end

-- ── Set channel variables for CDR telemetry ──────────────────────────────────
-- HARD REQUIREMENT: These MUST be set BEFORE result_event:fire() so that
-- CHANNEL_EXECUTE_COMPLETE carries them and Python can read them.
-- They are also read by handlers.py on CHANNEL_HANGUP_COMPLETE for CDR.

if session:ready() then
    session:setVariable("amd_result", final_result)
    session:setVariable("amd_layer", final_layer)
    session:setVariable("amd_decision_ms", tostring(final_decision_ms))
    session:setVariable("amd_confidence", tostring(final_confidence))
    if final_transcript ~= "" then
        session:setVariable("amd_transcript", final_transcript)
    end
end

freeswitch.consoleLog("INFO",
    "[AMD] Final decision on " .. uuid ..
    ": result=" .. final_result ..
    " layer=" .. final_layer ..
    " confidence=" .. final_confidence ..
    " elapsed=" .. final_decision_sec .. "s\n"
)

-- ── Fire amd::result CUSTOM event (telemetry only) ───────────────────────────
-- This is the LAST action before hangup/return.  By this point:
--   1. All session:execute() cleanup is done (avmd stop)
--   2. All channel variables are set (amd_result, amd_layer, etc.)
--   3. Python receives this for database counters and test logs
--   4. For HUMAN results, Python starts IVR via CHANNEL_EXECUTE_COMPLETE
--      (which fires AFTER this script returns and frees the channel thread)

local result_event = freeswitch.Event("CUSTOM", "amd::result")
result_event:addHeader("Unique-ID", uuid)
result_event:addHeader("variable_amd_result", final_result)
result_event:addHeader("variable_amd_layer", final_layer)
result_event:addHeader("variable_amd_decision_ms", tostring(final_decision_ms))
result_event:addHeader("variable_amd_confidence", tostring(final_confidence))
result_event:addHeader("variable_amd_transcript", final_transcript)
result_event:addHeader("variable_campaign_id", campaign_id)
result_event:addHeader("variable_campaign_mode", campaign_mode)
result_event:addHeader("variable_vm_drop_audio_id", vm_drop_audio_id)
result_event:addHeader("variable_is_test_call", session:getVariable("is_test_call") or "false")
result_event:fire()

freeswitch.consoleLog("INFO", "[AMD] Fired amd::result event for " .. uuid .. "\n")

-- ── Post-Event: Hangup if needed ─────────────────────────────────────────────
-- ONLY session:hangup() is allowed here — NO more session:execute() calls.
-- For HUMAN results, this script simply returns.  CHANNEL_EXECUTE_COMPLETE
-- fires for the "lua" app, Python reads variable_amd_result == "human"
-- from the event, and starts IVR on the now-free channel thread.

if not session:ready() then
    return
end

if final_result == "machine" and campaign_mode ~= "B" then
    -- MACHINE + Mode A/C: Hangup immediately (zero SIP waste)
    -- session:hangup() fires synchronously in the FS media thread.
    freeswitch.consoleLog("INFO",
        "[AMD] MACHINE + Mode " .. campaign_mode .. " — executing session:hangup()\n")
    session:hangup("NORMAL_CLEARING")

elseif final_result == "unknown" then
    -- UNKNOWN + Mode A/B: Hangup immediately
    -- (Mode C was already overridden to "human" above, so won't reach here)
    freeswitch.consoleLog("INFO",
        "[AMD] UNKNOWN + Mode " .. campaign_mode .. " — executing session:hangup()\n")
    session:hangup("NORMAL_CLEARING")
end

-- For HUMAN and MACHINE+Mode_B: script returns, channel stays alive.
-- CHANNEL_EXECUTE_COMPLETE for "lua" fires → Python starts IVR (human)
-- or waits for avmd::beep (machine mode B).
