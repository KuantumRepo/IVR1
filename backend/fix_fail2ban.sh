#!/bin/bash
# fix_fail2ban.sh — Properly configure fail2ban for Dockerized FreeSWITCH
# 
# Problem: FreeSWITCH runs in Docker with json-file log driver.
# Docker wraps each log line in JSON with ANSI escape codes.
# fail2ban's regex must handle this format to extract attacker IPs.
#
# Since FreeSWITCH uses --network host, standard iptables INPUT chain works.

set -e

echo "=== Fixing fail2ban for Dockerized FreeSWITCH ==="

# 1. Remove conflicting jail.d config (points to non-existent host log path)
rm -f /etc/fail2ban/jail.d/freeswitch.conf
echo "[OK] Removed conflicting jail.d/freeswitch.conf"

# 2. Find the FreeSWITCH container's JSON log file
FS_CONTAINER_ID=$(docker inspect ivr1-freeswitch-1 --format '{{.Id}}' 2>/dev/null)
if [ -z "$FS_CONTAINER_ID" ]; then
    echo "[ERROR] Cannot find ivr1-freeswitch-1 container"
    exit 1
fi
FS_LOG_PATH="/var/lib/docker/containers/${FS_CONTAINER_ID}/${FS_CONTAINER_ID}-json.log"
echo "[OK] FreeSWITCH log: $FS_LOG_PATH"

# 3. Write the filter
cat > /etc/fail2ban/filter.d/freeswitch.conf << 'FILTER'
# FreeSWITCH SIP auth failure filter for fail2ban
# Designed for Docker json-file log driver with ANSI color codes
#
# Log format (Docker json-file driver):
#   {"log":"\u001b[m\u001b[35m... [WARNING] sofia_reg.c:3210 Can't find user [ext@ip] from ATTACKER_IP\n","stream":"stdout","time":"2026-05-03T21:30:13.034Z"}
#
# Strategy:
#   datepattern: Extracts timestamp from Docker JSON "time" field
#   failregex: Matches FS log patterns. The .* at start of each line
#              skips the JSON envelope and ANSI escape codes.

[Definition]

# Parse timestamp from Docker JSON "time" field
datepattern = "time":"\d{4}-\d{2}-\d{2}T%H:%M:%S

# SIP scanners probing random/non-existent extensions
# SIP auth failures (wrong password for valid or invalid users)
failregex = Can't find user \[[^\]]*\] from <HOST>
            SIP auth failure \((?:REGISTER|INVITE)\) on sofia profile '[^']+' for \[[^\]]*\] from ip <HOST>

ignoreregex =
FILTER
echo "[OK] Filter written to /etc/fail2ban/filter.d/freeswitch.conf"

# 4. Write the jail config
cat > /etc/fail2ban/jail.local << JAIL
[DEFAULT]
# Whitelist: localhost, Docker internal, private subnets
ignoreip = 127.0.0.1/8 ::1 172.16.0.0/12 10.0.0.0/8

[sshd]
enabled = true

[freeswitch]
enabled  = true
filter   = freeswitch
backend  = auto
logpath  = ${FS_LOG_PATH}
port     = 5060,5061,5080,5081
protocol = all
# Aggressive: 3 failures in 5 minutes triggers a 24-hour ban
maxretry = 3
findtime = 300
bantime  = 86400
# Standard iptables on INPUT chain (FreeSWITCH uses --network host)
action   = iptables-allports[name=freeswitch, protocol=all]
JAIL
echo "[OK] Jail written to /etc/fail2ban/jail.local"

# 5. Test the regex against the actual log
echo ""
echo "=== Testing regex against live log (last 1000 lines) ==="
tail -1000 "$FS_LOG_PATH" > /tmp/fs_log_sample.txt
fail2ban-regex /tmp/fs_log_sample.txt /etc/fail2ban/filter.d/freeswitch.conf 2>&1 || true
rm -f /tmp/fs_log_sample.txt

# 6. Restart fail2ban
echo ""
echo "=== Restarting fail2ban ==="
systemctl restart fail2ban
sleep 2

# 7. Verify
echo ""
echo "=== Verification ==="
fail2ban-client status
echo ""
fail2ban-client status freeswitch
echo ""
echo "=== Done ==="
