#!/bin/bash
# ================================================================
# DTMF Diagnostic Script — Raw audio capture + SpanDSP verbose
# Fires 2 simultaneous calls, records audio, checks negotiation
# ================================================================
set -e

FS="sudo docker exec ivr1-freeswitch-1 /usr/local/freeswitch/bin/fs_cli -p z0X3WoErw9AFprB19KiYKhTf -x"
PROMPT="/audio/tts_12100a5a-0ede-4119-bb3a-0eec54ae2d24.wav"
GW="a6a3c1f5-f3fc-45ff-a042-f66ffc0b3392"

UUID1="d1a90001-0001-0001-0001-000000000001"
UUID2="d1a90002-0002-0002-0002-000000000002"

TARGET1="+18187320828"
TARGET2="+13102901556"
CID1="18187320199"
CID2="13102901199"

echo "================================================================"
echo "  DTMF DIAGNOSTIC — RAW AUDIO CAPTURE + SPANDSP VERBOSE"
echo "================================================================"

# 1. Set FS log level to DEBUG to capture SpanDSP verbose output
echo "[1] Setting FreeSWITCH log level to DEBUG..."
$FS "console loglevel 7" 2>/dev/null || true
$FS "sofia loglevel all 7" 2>/dev/null || true

# 2. Originate both calls with diagnostic channel variables
echo "[2] Originating Call 1: $CID1 -> $TARGET1"
VARS1="{origination_uuid=${UUID1},origination_caller_id_number=${CID1},origination_caller_id_name=Local Call,dtmf_type=none,ignore_early_media=true,execute_on_answer='record_session /tmp/diag_call1.wav'}"
$FS "bgapi originate ${VARS1}sofia/gateway/${GW}/${TARGET1} &playback(${PROMPT})" &

sleep 1

echo "[2] Originating Call 2: $CID2 -> $TARGET2"
VARS2="{origination_uuid=${UUID2},origination_caller_id_number=${CID2},origination_caller_id_name=Local Call,dtmf_type=none,ignore_early_media=true,execute_on_answer='record_session /tmp/diag_call2.wav'}"
$FS "bgapi originate ${VARS2}sofia/gateway/${GW}/${TARGET2} &playback(${PROMPT})" &

echo ""
echo "================================================================"
echo "  CALLS FIRING — PICK UP BOTH PHONES AND PRESS 1"
echo "  Waiting 45 seconds for you to answer and press digits..."
echo "================================================================"
echo ""

# 3. Wait for calls to be answered, then enable SpanDSP on both
sleep 5
echo "[3] Enabling spandsp_start_dtmf on both channels..."
$FS "uuid_broadcast ${UUID1} spandsp_start_dtmf both" 2>/dev/null || true
$FS "uuid_broadcast ${UUID2} spandsp_start_dtmf both" 2>/dev/null || true

# 4. Wait for digit press
sleep 40

# 5. Capture diagnostic data BEFORE the channels die
echo ""
echo "================================================================"
echo "  DIAGNOSTIC DATA CAPTURE"
echo "================================================================"

echo ""
echo "--- Call 1 ($TARGET1) Channel Variables ---"
echo "dtmf_type:            $($FS "uuid_getvar ${UUID1} dtmf_type" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "rtp_2833_recv_payload: $($FS "uuid_getvar ${UUID1} rtp_2833_recv_payload" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "rtp_2833_send_payload: $($FS "uuid_getvar ${UUID1} rtp_2833_send_payload" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "read_codec:           $($FS "uuid_getvar ${UUID1} read_codec" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "write_codec:          $($FS "uuid_getvar ${UUID1} write_codec" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "remote_media_ip:      $($FS "uuid_getvar ${UUID1} remote_media_ip" 2>/dev/null || echo 'CHANNEL_GONE')"

echo ""
echo "--- Call 2 ($TARGET2) Channel Variables ---"
echo "dtmf_type:            $($FS "uuid_getvar ${UUID2} dtmf_type" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "rtp_2833_recv_payload: $($FS "uuid_getvar ${UUID2} rtp_2833_recv_payload" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "rtp_2833_send_payload: $($FS "uuid_getvar ${UUID2} rtp_2833_send_payload" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "read_codec:           $($FS "uuid_getvar ${UUID2} read_codec" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "write_codec:          $($FS "uuid_getvar ${UUID2} write_codec" 2>/dev/null || echo 'CHANNEL_GONE')"
echo "remote_media_ip:      $($FS "uuid_getvar ${UUID2} remote_media_ip" 2>/dev/null || echo 'CHANNEL_GONE')"

# 6. Kill calls if still up
$FS "uuid_kill ${UUID1}" 2>/dev/null || true
$FS "uuid_kill ${UUID2}" 2>/dev/null || true

# 7. Check recording files
echo ""
echo "--- Recording Files ---"
sudo docker exec ivr1-freeswitch-1 ls -lah /tmp/diag_call1.wav 2>/dev/null || echo "diag_call1.wav NOT FOUND"
sudo docker exec ivr1-freeswitch-1 ls -lah /tmp/diag_call2.wav 2>/dev/null || echo "diag_call2.wav NOT FOUND"

# 8. Copy recordings out of container
echo ""
echo "[8] Extracting recordings..."
sudo docker cp ivr1-freeswitch-1:/tmp/diag_call1.wav /home/ubuntu/diag_call1.wav 2>/dev/null || echo "Failed to extract call1 recording"
sudo docker cp ivr1-freeswitch-1:/tmp/diag_call2.wav /home/ubuntu/diag_call2.wav 2>/dev/null || echo "Failed to extract call2 recording"

# 9. Dump SpanDSP/DTMF lines from FS logs
echo ""
echo "--- SpanDSP / DTMF Log Lines (last 60 seconds) ---"
sudo docker logs --since 90s ivr1-freeswitch-1 2>&1 | grep -i 'spandsp\|dtmf\|INBAND\|digit\|tone' | tail -40

# 10. Reset log level
$FS "console loglevel 4" 2>/dev/null || true

echo ""
echo "================================================================"
echo "  DIAGNOSTIC COMPLETE"
echo "  Recordings saved to /home/ubuntu/diag_call1.wav and diag_call2.wav"
echo "================================================================"
