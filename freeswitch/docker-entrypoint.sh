#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════════════════
# FreeSWITCH Docker Entrypoint — Broadcaster Edition
# ═══════════════════════════════════════════════════════════════════════════════
#
# Adapted from the official FreeSWITCH Docker entrypoint:
#   https://github.com/signalwire/freeswitch/blob/master/docker/release/docker-entrypoint.sh
#
# Flow:
#   1. If config dir is empty, copy vanilla config as a starting point
#   2. chown all FS directories to the freeswitch user
#   3. Run any hook scripts in /docker-entrypoint.d/
#   4. Drop privileges via gosu and exec FreeSWITCH
# ═══════════════════════════════════════════════════════════════════════════════

FS_PREFIX="/usr/local/freeswitch"

if [ "$1" = 'freeswitch' ]; then

    # ── Copy vanilla config if no config is mounted ─────────────────────────
    # When you volume-mount your own conf/ directory, this is skipped.
    # If the mount is empty (first run), seed it from the vanilla defaults.
    if [ ! -f "${FS_PREFIX}/etc/freeswitch/freeswitch.xml" ]; then
        echo "No freeswitch.xml found — copying vanilla config..."
        mkdir -p "${FS_PREFIX}/etc/freeswitch"
        if [ -d "${FS_PREFIX}/share/freeswitch/conf/vanilla" ]; then
            cp -varf "${FS_PREFIX}/share/freeswitch/conf/vanilla/"* "${FS_PREFIX}/etc/freeswitch/"
        fi
    fi

    # ── Fix ownership ───────────────────────────────────────────────────────
    chown -R freeswitch:freeswitch "${FS_PREFIX}/etc/freeswitch" 2>/dev/null || true
    chown -R freeswitch:freeswitch /var/run/freeswitch 2>/dev/null || true
    chown -R freeswitch:freeswitch /var/lib/freeswitch 2>/dev/null || true
    chown -R freeswitch:freeswitch "${FS_PREFIX}/log" 2>/dev/null || true
    chown -R freeswitch:freeswitch "${FS_PREFIX}/run" 2>/dev/null || true
    chown -R freeswitch:freeswitch "${FS_PREFIX}/db" 2>/dev/null || true

    # ── Inject external IP and Password from environment ──────────────────────
    # vars.xml defaults to stun:stun.freeswitch.org for public IP discovery.
    # In production, we override with the deterministic IP from .env to avoid
    # STUN latency, boot delays, and incorrect resolution behind NAT.
    # The sed is idempotent — once replaced, the search string is gone.
    VARS_FILE="${FS_PREFIX}/etc/freeswitch/vars.xml"
    if [ -f "$VARS_FILE" ]; then
        if [ -n "$EXT_RTP_IP" ] && [ "$EXT_RTP_IP" != "stun:stun.freeswitch.org" ]; then
            sed -i "s|external_rtp_ip=stun:stun.freeswitch.org|external_rtp_ip=${EXT_RTP_IP}|g" "$VARS_FILE"
            echo "Injected external_rtp_ip=${EXT_RTP_IP}"
        fi
        if [ -n "$EXT_SIP_IP" ] && [ "$EXT_SIP_IP" != "stun:stun.freeswitch.org" ]; then
            sed -i "s|external_sip_ip=stun:stun.freeswitch.org|external_sip_ip=${EXT_SIP_IP}|g" "$VARS_FILE"
            echo "Injected external_sip_ip=${EXT_SIP_IP}"
        fi
        # ── Set SIP domain to public IP ─────────────────────────────────────
        # On AWS EC2, $${local_ip_v4} resolves to the private IP (172.31.x.x).
        # Agent softphones register from external networks using the public IP,
        # so the FS domain must match the public IP to find users in the directory.
        if [ -n "$FS_SIP_DOMAIN" ] && [ "$FS_SIP_DOMAIN" != "127.0.0.1" ]; then
            sed -i 's|data="domain=\$\${local_ip_v4}"|data="domain='"${FS_SIP_DOMAIN}"'"|g' "$VARS_FILE"
            echo "Injected SIP domain=${FS_SIP_DOMAIN}"
        fi
    fi

    ESL_CONF_FILE="${FS_PREFIX}/etc/freeswitch/autoload_configs/event_socket.conf.xml"
    if [ -f "$ESL_CONF_FILE" ]; then
        if [ -n "$FS_ESL_PASSWORD" ]; then
            sed -i -E "s|<param name=\"password\" value=\"[^\"]+\"/>|<param name=\"password\" value=\"${FS_ESL_PASSWORD}\"/>|g" "$ESL_CONF_FILE"
            echo "Injected FS_ESL_PASSWORD into event_socket.conf.xml"
        fi
    fi

    # ── Security: Purge vanilla default users ─────────────────────────────
    # The vanilla FreeSWITCH config ships with extensions 1000-1019 using
    # password "1234". SIP scanners WILL crack these within hours and use
    # your gateways for toll fraud. Our backend provisions real agents
    # dynamically via generate_agent_xml() with cryptographic passwords.
    DIRECTORY_DIR="${FS_PREFIX}/etc/freeswitch/directory/default"
    if [ -d "$DIRECTORY_DIR" ]; then
        PURGED=0
        for f in "$DIRECTORY_DIR"/100[0-9].xml \
                 "$DIRECTORY_DIR"/101[0-9].xml \
                 "$DIRECTORY_DIR"/brian.xml \
                 "$DIRECTORY_DIR"/default.xml \
                 "$DIRECTORY_DIR"/example.com.xml \
                 "$DIRECTORY_DIR"/skinny-example.xml; do
            if [ -f "$f" ] && grep -q 'default_password' "$f" 2>/dev/null; then
                rm -f "$f"
                PURGED=$((PURGED + 1))
            fi
        done
        [ $PURGED -gt 0 ] && echo "Security: purged $PURGED vanilla user(s) with default_password"
    fi

    # ── Run hook scripts ────────────────────────────────────────────────────
    # Drop any .sh files in /docker-entrypoint.d/ to run custom init logic
    # (e.g., generating gateway configs, setting environment-specific vars).
    if [ -d /docker-entrypoint.d ]; then
        for f in /docker-entrypoint.d/*.sh; do
            [ -f "$f" ] && echo "Running entrypoint hook: $f" && . "$f"
        done
    fi

    # ── Start FreeSWITCH ────────────────────────────────────────────────────
    # Drop privileges and exec as the freeswitch user.
    # -nonat:  Disable NAT traversal (we handle NAT via ext-rtp-ip/ext-sip-ip)
    # -c:      Run in console mode (foreground — Docker best practice)
    echo "Starting FreeSWITCH as user 'freeswitch'..."
    exec gosu freeswitch "${FS_PREFIX}/bin/freeswitch" \
        -u freeswitch \
        -g freeswitch \
        -nonat \
        -c
fi

# If the first argument is NOT "freeswitch", execute whatever was passed
# (allows running fs_cli, bash, etc. inside the container)
exec "$@"
