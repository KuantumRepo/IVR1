-- amd.lua
-- Energy heuristic-based Answering Machine Detection script for FreeSWITCH
-- Uses wait_for_silence to detect the length of the initial greeting.

freeswitch.consoleLog("info", "AMD Lua: Starting analysis on " .. session:get_uuid() .. "\n")

-- Answer if not answered
if not session:ready() then return end
session:answer()

-- Give it a tiny bit of time to settle audio
session:sleep(500)

-- Configuration for wait_for_silence
local silence_thresh = 400 -- Energy threshold
local silence_hits = 15     -- Consecutive silence frames to trigger (approx 300ms)
local listen_timeout = 5000 -- Max time to wait for silence in ms

-- Wait for the person to STOP talking
-- "wait_for_silence" waits until it detects silence. If the person keeps talking
-- for more than listen_timeout, it returns false (timeout).

local start_time = os.time()
local status = session:execute("wait_for_silence", silence_thresh .. " " .. silence_hits .. " " .. listen_timeout)
local duration = os.time() - start_time

freeswitch.consoleLog("info", "AMD Lua: Initial greeting duration approx " .. duration .. " seconds\n")

if duration > 3 then
    -- A greeting longer than 3 seconds usually implies a voicemail prompt
    -- e.g. "Hi, you have reached the voicemail of..."
    session:setVariable("amd_status", "MACHINE")
    freeswitch.consoleLog("info", "AMD Lua: Result MACHINE\n")
else
    -- Short greeting, e.g. "Hello?", "Yes?"
    session:setVariable("amd_status", "HUMAN")
    freeswitch.consoleLog("info", "AMD Lua: Result HUMAN\n")
end

-- Fire the CUSTOM amd::info event so handlers.py can catch it!
local event = freeswitch.Event("CUSTOM", "amd::info")
event:addHeader("Unique-ID", session:get_uuid())
event:addHeader("variable_amd_result", session:getVariable("amd_status"))
event:addHeader("variable_campaign_id", session:getVariable("campaign_id") or "")
event:fire()
