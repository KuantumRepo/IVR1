"""
Test script: Verify the parser fix for multi-agent registration display.

Reproduces the bug with the EXACT output format captured from production 
FreeSWitch (v1.10, built from source, container: ivr1-freeswitch-1).

Tests both:
  - OLD parser (_parse_sofia_registrations) — broken, only returns last agent
  - NEW parser (_parse_sofia_registrations_xml) — fixed, returns all agents
"""

import re
import xml.etree.ElementTree as ET


# ═══════════════════════════════════════════════════════════════════
# OLD PARSER (broken — from backend/app/api/v1/agents.py before fix)
# ═══════════════════════════════════════════════════════════════════
def _parse_sofia_registrations_OLD(raw: str | None) -> dict[str, dict]:
    result = {}
    if not raw:
        return result
    blocks = re.split(r'={3,}', raw)
    for block in blocks:
        lines = block.strip().split('\n')
        user = None
        agent = None
        status = None
        for line in lines:
            line = line.strip()
            if line.startswith('User:'):
                user_part = line.split(':', 1)[1].strip()
                user = user_part.split('@')[0] if '@' in user_part else user_part
            elif line.startswith('Agent:'):
                agent = line.split(':', 1)[1].strip()
            elif line.startswith('Status:'):
                status = line.split(':', 1)[1].strip()
        if user and status and 'Registered' in status:
            result[user] = {"user_agent": agent, "status": status}
    return result


# ═══════════════════════════════════════════════════════════════════
# NEW PARSER (fixed — XML-based)
# ═══════════════════════════════════════════════════════════════════
def _parse_sofia_registrations_xml(raw: str | None) -> dict[str, dict]:
    result = {}
    if not raw:
        return result
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return result
    for reg in root.findall('.//registration'):
        user_el = reg.find('user')
        agent_el = reg.find('agent')
        status_el = reg.find('status')
        sip_auth_user_el = reg.find('sip-auth-user')
        if user_el is None or status_el is None:
            continue
        status_text = status_el.text or ''
        if 'Registered' not in status_text:
            continue
        if sip_auth_user_el is not None and sip_auth_user_el.text:
            ext = sip_auth_user_el.text.strip()
        else:
            user_text = user_el.text or ''
            ext = user_text.split('@')[0] if '@' in user_text else user_text
        result[ext] = {
            "user_agent": agent_el.text.strip() if agent_el is not None and agent_el.text else None,
            "status": status_text.strip(),
        }
    return result


# ═══════════════════════════════════════════════════════════════════
# TEST DATA: Text format (from production fs_cli)
# ═══════════════════════════════════════════════════════════════════
MULTI_AGENT_TEXT = """
Registrations:
=================================================================================================
Call-ID:    \tXGJ0nkFwfg6j1VfOl6pbxA..
User:       \t3002@18.218.221.240
Contact:    \t"3002" <sip:3002@23.234.105.118:8380>
Agent:      \tPortSIP UC Client  Android - v13.2.9
Status:     \tRegistered(UDP)(unknown) EXP(2026-05-02 20:42:02) EXPSECS(233)
Ping-Status:\tReachable
Ping-Time:\t0.00
Host:       \tip-172-31-43-255
IP:         \t23.234.105.118
Port:       \t8380
Auth-User:  \t3002
Auth-Realm: \t18.218.221.240
MWI-Account:\t3002@18.218.221.240

Call-ID:    \tABC123DEF456@192.168.1.50
User:       \t3001@18.218.221.240
Contact:    \t"3001" <sip:3001@10.0.0.5:5060>
Agent:      \tMicroSIP/3.21.3
Status:     \tRegistered(UDP)(unknown) EXP(2026-05-02 20:45:00) EXPSECS(400)
Ping-Status:\tReachable
Ping-Time:\t0.00
Host:       \tip-172-31-43-255
IP:         \t10.0.0.5
Port:       \t5060
Auth-User:  \t3001
Auth-Realm: \t18.218.221.240
MWI-Account:\t3001@18.218.221.240

Call-ID:    \tDEF789GHI012@192.168.1.60
User:       \t3003@18.218.221.240
Contact:    \t"3003" <sip:3003@10.0.0.6:5060>
Agent:      \tLinphone/5.0.0
Status:     \tRegistered(UDP)(unknown) EXP(2026-05-02 20:50:00) EXPSECS(600)
Ping-Status:\tReachable
Ping-Time:\t0.00
Host:       \tip-172-31-43-255
IP:         \t10.0.0.6
Port:       \t5060
Auth-User:  \t3003
Auth-Realm: \t18.218.221.240
MWI-Account:\t3003@18.218.221.240

Total items returned: 3
=================================================================================================

"""

# ═══════════════════════════════════════════════════════════════════
# TEST DATA: XML format (from production sofia xmlstatus)
# ═══════════════════════════════════════════════════════════════════
MULTI_AGENT_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<profile>
  <registrations>
    <registration>
        <call-id>XGJ0nkFwfg6j1VfOl6pbxA..</call-id>
        <user>3002@18.218.221.240</user>
        <contact>&quot;3002&quot; &lt;sip:3002@23.234.105.118:8380&gt;</contact>
        <agent>PortSIP UC Client  Android - v13.2.9</agent>
        <status>Registered(UDP)(unknown) exp(2026-05-02 20:42:02) expsecs(233)</status>
        <ping-status>Reachable</ping-status>
        <ping-time>0.00</ping-time>
        <host>ip-172-31-43-255</host>
        <network-ip>23.234.105.118</network-ip>
        <network-port>8380</network-port>
        <sip-auth-user>3002</sip-auth-user>
        <sip-auth-realm>18.218.221.240</sip-auth-realm>
        <mwi-account>3002@18.218.221.240</mwi-account>
    </registration>
    <registration>
        <call-id>ABC123DEF456@192.168.1.50</call-id>
        <user>3001@18.218.221.240</user>
        <contact>&quot;3001&quot; &lt;sip:3001@10.0.0.5:5060&gt;</contact>
        <agent>MicroSIP/3.21.3</agent>
        <status>Registered(UDP)(unknown) exp(2026-05-02 20:45:00) expsecs(400)</status>
        <ping-status>Reachable</ping-status>
        <ping-time>0.00</ping-time>
        <host>ip-172-31-43-255</host>
        <network-ip>10.0.0.5</network-ip>
        <network-port>5060</network-port>
        <sip-auth-user>3001</sip-auth-user>
        <sip-auth-realm>18.218.221.240</sip-auth-realm>
        <mwi-account>3001@18.218.221.240</mwi-account>
    </registration>
    <registration>
        <call-id>DEF789GHI012@192.168.1.60</call-id>
        <user>3003@18.218.221.240</user>
        <contact>&quot;3003&quot; &lt;sip:3003@10.0.0.6:5060&gt;</contact>
        <agent>Linphone/5.0.0</agent>
        <status>Registered(UDP)(unknown) exp(2026-05-02 20:50:00) expsecs(600)</status>
        <ping-status>Reachable</ping-status>
        <ping-time>0.00</ping-time>
        <host>ip-172-31-43-255</host>
        <network-ip>10.0.0.6</network-ip>
        <network-port>5060</network-port>
        <sip-auth-user>3003</sip-auth-user>
        <sip-auth-realm>18.218.221.240</sip-auth-realm>
        <mwi-account>3003@18.218.221.240</mwi-account>
    </registration>
  </registrations>
</profile>
"""

# ═══════════════════════════════════════════════════════════════════
# TEST DATA: Single agent XML (from production)
# ═══════════════════════════════════════════════════════════════════
SINGLE_AGENT_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<profile>
  <registrations>
    <registration>
        <call-id>XGJ0nkFwfg6j1VfOl6pbxA..</call-id>
        <user>3002@18.218.221.240</user>
        <contact>&quot;3002&quot; &lt;sip:3002@23.234.105.118:8380&gt;</contact>
        <agent>PortSIP UC Client  Android - v13.2.9</agent>
        <status>Registered(UDP)(unknown) exp(2026-05-02 20:42:02) expsecs(225)</status>
        <ping-status>Reachable</ping-status>
        <ping-time>0.00</ping-time>
        <host>ip-172-31-43-255</host>
        <network-ip>23.234.105.118</network-ip>
        <network-port>8380</network-port>
        <sip-auth-user>3002</sip-auth-user>
        <sip-auth-realm>18.218.221.240</sip-auth-realm>
        <mwi-account>3002@18.218.221.240</mwi-account>
    </registration>
  </registrations>
</profile>
"""

# ═══════════════════════════════════════════════════════════════════
# TEST DATA: Empty registrations
# ═══════════════════════════════════════════════════════════════════
EMPTY_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<profile>
  <registrations>
  </registrations>
</profile>
"""


# ═══════════════════════════════════════════════════════════════════
# RUN TESTS
# ═══════════════════════════════════════════════════════════════════
passed = 0
failed = 0

def check(test_name, actual, expected):
    global passed, failed
    if actual == expected:
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name}")
        print(f"     Expected: {expected}")
        print(f"     Got:      {actual}")
        failed += 1


print("=" * 70)
print("OLD PARSER — Proving the bug")
print("=" * 70)
result = _parse_sofia_registrations_OLD(MULTI_AGENT_TEXT)
check("3 agents registered -> old parser returns only 1", len(result), 1)
check("Only last agent (3003) survives", list(result.keys()), ['3003'])

print()
print("=" * 70)
print("NEW PARSER (XML) — Verifying the fix")
print("=" * 70)

# Test 1: Single agent
result = _parse_sofia_registrations_xml(SINGLE_AGENT_XML)
check("Single agent: count", len(result), 1)
check("Single agent: ext 3002 present", '3002' in result, True)
check("Single agent: user_agent", result['3002']['user_agent'], 'PortSIP UC Client  Android - v13.2.9')

# Test 2: Multiple agents
result = _parse_sofia_registrations_xml(MULTI_AGENT_XML)
check("Multi agent: count", len(result), 3)
check("Multi agent: 3001 present", '3001' in result, True)
check("Multi agent: 3002 present", '3002' in result, True)
check("Multi agent: 3003 present", '3003' in result, True)
check("Multi agent: 3001 user_agent", result['3001']['user_agent'], 'MicroSIP/3.21.3')
check("Multi agent: 3002 user_agent", result['3002']['user_agent'], 'PortSIP UC Client  Android - v13.2.9')
check("Multi agent: 3003 user_agent", result['3003']['user_agent'], 'Linphone/5.0.0')

# Test 3: Empty registrations
result = _parse_sofia_registrations_xml(EMPTY_XML)
check("Empty registrations: count", len(result), 0)

# Test 4: None input
result = _parse_sofia_registrations_xml(None)
check("None input: count", len(result), 0)

# Test 5: Garbage input
result = _parse_sofia_registrations_xml("not xml at all")
check("Garbage input: count", len(result), 0)

print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)

exit(1 if failed > 0 else 0)
