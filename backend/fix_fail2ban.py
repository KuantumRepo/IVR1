#!/usr/bin/env python3
"""Write the correct fail2ban filter + jail config for Dockerized FreeSWITCH."""
import subprocess, os, sys

# 1. Find the FreeSWITCH container's log path
result = subprocess.run(
    ["docker", "inspect", "ivr1-freeswitch-1", "--format", "{{.Id}}"],
    capture_output=True, text=True
)
container_id = result.stdout.strip()
if not container_id:
    print("[ERROR] Cannot find ivr1-freeswitch-1 container")
    sys.exit(1)

log_path = f"/var/lib/docker/containers/{container_id}/{container_id}-json.log"
print(f"[OK] FreeSWITCH container log: {log_path}")

# 2. Write the filter config
# The %% is how fail2ban's configparser (Python's configparser) requires
# literal % characters to be escaped.
filter_content = r"""# FreeSWITCH SIP auth failure filter for fail2ban
# Designed for Docker json-file log driver with ANSI escape codes
#
# Docker wraps each FreeSWITCH log line in JSON:
#   {"log":"\u001b[m\u001b[35m2026-05-03 ... [WARNING] sofia_reg.c:3210 Can't find user [ext@ip] from ATTACKER_IP\n","stream":"stdout","time":"2026-05-03T21:30:13.034Z"}
#
# datepattern: Uses the Docker JSON "time" field for timestamp detection.
# failregex:   Matches FS auth failure patterns anywhere in the line.

[Definition]

# Docker JSON timestamp field (double %% for configparser escaping)
datepattern = "time":"\d{4}-\d{2}-\d{2}T%%H:%%M:%%S

# SIP scanner probing non-existent extensions
# SIP auth failures (wrong password attempts)
failregex = Can't find user \[[^\]]*\] from <HOST>
            SIP auth failure \((?:REGISTER|INVITE)\) on sofia profile '[^']+' for \[[^\]]*\] from ip <HOST>

ignoreregex =
"""

with open("/etc/fail2ban/filter.d/freeswitch.conf", "w") as f:
    f.write(filter_content)
print("[OK] Filter written to /etc/fail2ban/filter.d/freeswitch.conf")

# 3. Remove conflicting jail.d config
conflicting = "/etc/fail2ban/jail.d/freeswitch.conf"
if os.path.exists(conflicting):
    os.unlink(conflicting)
    print(f"[OK] Removed conflicting {conflicting}")

# 4. Write consolidated jail config
jail_content = f"""[DEFAULT]
# Whitelist: localhost, Docker internal, private subnets
ignoreip = 127.0.0.1/8 ::1 172.16.0.0/12 10.0.0.0/8

[sshd]
enabled = true

[freeswitch]
enabled  = true
filter   = freeswitch
backend  = auto
logpath  = {log_path}
port     = 5060,5061,5080,5081
protocol = all
# 3 failures in 5 minutes → 24 hour ban
maxretry = 3
findtime = 300
bantime  = 86400
# iptables INPUT chain (FreeSWITCH uses --network host)
action   = iptables-allports[name=freeswitch, protocol=all]
"""

with open("/etc/fail2ban/jail.local", "w") as f:
    f.write(jail_content)
print("[OK] Jail written to /etc/fail2ban/jail.local")

# 5. Test regex against a sample of the actual log
print("\n=== Testing regex against last 500 log lines ===")
# Extract last 500 lines to a temp file
subprocess.run(["bash", "-c", f"tail -500 '{log_path}' > /tmp/f2b_test_sample.log"])
result = subprocess.run(
    ["fail2ban-regex", "/tmp/f2b_test_sample.log", "/etc/fail2ban/filter.d/freeswitch.conf"],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
os.unlink("/tmp/f2b_test_sample.log")

# 6. Restart fail2ban
print("\n=== Restarting fail2ban ===")
subprocess.run(["systemctl", "restart", "fail2ban"])
import time; time.sleep(3)

# 7. Verify
print("\n=== Verification ===")
result = subprocess.run(["fail2ban-client", "status"], capture_output=True, text=True)
print(result.stdout)
result = subprocess.run(["fail2ban-client", "status", "freeswitch"], capture_output=True, text=True)
print(result.stdout)
print("=== Done ===")
