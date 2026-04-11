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
