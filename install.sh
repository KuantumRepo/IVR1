#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════════════════
# Broadcaster — Interactive Production Deployment Script
# ═══════════════════════════════════════════════════════════════════════════════
#
# This script fully deploys the Broadcaster stack on a fresh Linux VPS.
# It is interactive — it will prompt you for all required values.
#
# Prerequisites (see DEPLOYMENT.md):
#   - Ubuntu 22.04+ / Debian 12+
#   - Docker Engine + Docker Compose V2 installed
#   - Root or sudo access
#   - A public IPv4 address
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

# ── Colors & Helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}ℹ ${NC} $1"; }
success() { echo -e "${GREEN}✅${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠️ ${NC} $1"; }
error()   { echo -e "${RED}❌${NC} $1"; }
header()  { echo -e "\n${BOLD}═══════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}  $1${NC}"; echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}\n"; }
divider() { echo -e "${CYAN}───────────────────────────────────────────────────────${NC}"; }

# ── Preflight Checks ─────────────────────────────────────────────────────────
header "Broadcaster — Production Deployment"

echo -e "This script will deploy the full Broadcaster stack on this server."
echo -e "It will prompt you for all required configuration values.\n"

# Check root / sudo
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root or with sudo."
    echo "  Run: sudo ./install.sh"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker is not installed."
    echo ""
    echo "  Install it with:"
    echo "    curl -fsSL https://get.docker.com | sh"
    echo ""
    echo "  Then re-run this script."
    exit 1
fi
success "Docker found: $(docker --version | head -1)"

# Check Docker Compose V2
if ! docker compose version &> /dev/null; then
    error "Docker Compose V2 is not available."
    echo "  Docker Compose V2 ships with Docker Engine 20.10+."
    echo "  Update Docker: curl -fsSL https://get.docker.com | sh"
    exit 1
fi
success "Docker Compose found: $(docker compose version | head -1)"

# ── Detect Public IP ─────────────────────────────────────────────────────────
divider
info "Detecting your server's public IP address..."

DETECTED_IP=""
# Try multiple services for reliability
for svc in "https://ifconfig.me" "https://api.ipify.org" "https://icanhazip.com"; do
    DETECTED_IP=$(curl -sf --max-time 5 "$svc" 2>/dev/null | tr -d '[:space:]') && break
done

if [ -n "$DETECTED_IP" ]; then
    success "Detected public IP: ${BOLD}${DETECTED_IP}${NC}"
else
    warn "Could not detect public IP automatically."
fi

# ── Interactive Configuration ─────────────────────────────────────────────────
header "Configuration"

echo -e "Please provide the following values. Press Enter to accept defaults.\n"

# --- Public IP ---
if [ -n "$DETECTED_IP" ]; then
    read -p "$(echo -e "${BOLD}Server Public IP${NC} [$DETECTED_IP]: ")" PUBLIC_IP
    PUBLIC_IP=${PUBLIC_IP:-$DETECTED_IP}
else
    while [ -z "$PUBLIC_IP" ]; do
        read -p "$(echo -e "${BOLD}Server Public IP${NC} (required): ")" PUBLIC_IP
    done
fi
success "Public IP: $PUBLIC_IP"

# --- Domain ---
echo ""
read -p "$(echo -e "${BOLD}Domain name${NC} for the web UI (e.g., app.yourdomain.com) [${PUBLIC_IP}]: ")" DOMAIN_NAME
DOMAIN_NAME=${DOMAIN_NAME:-$PUBLIC_IP}
success "Domain: $DOMAIN_NAME"

# --- Deployment Method ---
echo ""
info "How do you want to deploy the Docker containers?"
echo "  1) Build locally from source (Bypasses GHCR free-tier limits, takes ~20 mins)"
echo "  2) Pull pre-built images from GHCR (Fast, requires working GitHub Actions)"
read -p "$(echo -e "${BOLD}Select method (1/2)${NC} [1]: ")" DEPLOY_METHOD
DEPLOY_METHOD=${DEPLOY_METHOD:-1}

if [ "$DEPLOY_METHOD" = "1" ]; then
    COMPOSE_FILE="docker-compose.yml"
    success "Method: Build locally ($COMPOSE_FILE)"
else
    COMPOSE_FILE="docker-compose.prod.yml"
    success "Method: Pull from GHCR ($COMPOSE_FILE)"

    # --- GitHub Container Registry ---
    echo ""
    info "Since you are pulling from GHCR, please provide your GitHub username."
    while [ -z "$GH_USER" ]; do
        read -p "$(echo -e "${BOLD}GitHub username or org${NC} (image owner): ")" GH_USER
    done
    success "Registry: ghcr.io/$GH_USER"
fi

# --- ESL Password ---
echo ""
read -p "$(echo -e "${BOLD}FreeSWITCH ESL password${NC} [auto-generate]: ")" ESL_PASSWORD_INPUT
if [ -n "$ESL_PASSWORD_INPUT" ]; then
    ESL_PASSWORD="$ESL_PASSWORD_INPUT"
else
    ESL_PASSWORD=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 24 | head -n 1)
    info "Generated ESL password."
fi

# --- DB Password ---
# CRITICAL: PostgreSQL only sets the password at first init (when the volume is
# empty). If a postgres_data volume already exists, we MUST reuse the existing
# password — otherwise the backend can't authenticate.
EXISTING_DB_PW=""
if docker volume inspect ivr1_postgres_data &>/dev/null || docker volume inspect postgres_data &>/dev/null; then
    # Volume exists — try to read password from existing .env
    if [ -f ".env" ]; then
        EXISTING_DB_PW=$(grep '^DB_PASSWORD=' .env | cut -d'=' -f2)
    elif [ -f ".env.backup" ]; then
        EXISTING_DB_PW=$(grep '^DB_PASSWORD=' .env.backup | cut -d'=' -f2)
    fi
fi

if [ -n "$EXISTING_DB_PW" ]; then
    warn "Existing database detected — reusing current password to prevent auth mismatch."
    info "To change the DB password, run: docker exec -it ivr1-postgres-1 psql -U broadcaster -c \"ALTER USER broadcaster WITH PASSWORD 'NEW_PW';\""
    DB_PASSWORD="$EXISTING_DB_PW"
else
    read -p "$(echo -e "${BOLD}Database password${NC} [auto-generate]: ")" DB_PASSWORD_INPUT
    if [ -n "$DB_PASSWORD_INPUT" ]; then
        DB_PASSWORD="$DB_PASSWORD_INPUT"
    else
        DB_PASSWORD=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 24 | head -n 1)
        info "Generated database password."
    fi
fi

# ── Authentication Credentials ──────────────────────────────────────────────
divider
echo ""
info "Setting up authentication (Username + Password + TOTP 2FA)..."
echo ""

# --- Auth Username ---
read -p "$(echo -e "${BOLD}Admin username${NC} [admin]: ")" AUTH_USERNAME_INPUT
AUTH_USERNAME=${AUTH_USERNAME_INPUT:-admin}
success "Username: $AUTH_USERNAME"

# --- Auth Password ---
echo ""
while [ -z "$AUTH_PASSWORD_INPUT" ]; do
    read -sp "$(echo -e "${BOLD}Admin password${NC} (required, will be bcrypt-hashed): ")" AUTH_PASSWORD_INPUT
    echo ""
    if [ -z "$AUTH_PASSWORD_INPUT" ]; then
        warn "Password cannot be empty."
    fi
done

# --- Generate bcrypt hash + TOTP secret using a throwaway Docker container ---
# Why Docker? Because:
#   - Docker is already a hard prerequisite (checked at line 52)
#   - Host Python may not have pip, bcrypt, or pyotp installed
#   - PEP 668 (Ubuntu 22.04+) blocks pip install without --break-system-packages
#   - A throwaway container guarantees it works on ANY Linux with Docker
#   - Zero host pollution — nothing is installed on the system
info "Generating credentials (pulling python:3-alpine if needed)..."

AUTH_CREDS=$(echo "$AUTH_PASSWORD_INPUT" | docker run --rm -i python:3-alpine sh -c '
pip install -q bcrypt pyotp 2>/dev/null
python3 -c "
import sys, bcrypt, pyotp
pw = sys.stdin.readline().strip()
h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
secret = pyotp.random_base32()
print(h)
print(secret)
"')

AUTH_PASSWORD_HASH=$(echo "$AUTH_CREDS" | sed -n '1p')
TOTP_SECRET=$(echo "$AUTH_CREDS" | sed -n '2p')

if [ -z "$AUTH_PASSWORD_HASH" ] || [ -z "$TOTP_SECRET" ]; then
    error "Failed to generate auth credentials. Check Docker is running."
    exit 1
fi

success "Password hashed with bcrypt."
success "TOTP secret generated."

# --- JWT Secret (auto-generated, pure bash) ---
JWT_SECRET=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 48 | head -n 1)
success "JWT secret generated."

# --- Emergency Bypass Code (auto-generated, pure bash) ---
EMERGENCY_BYPASS_CODE=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 32 | head -n 1)
success "Emergency bypass code generated."

# --- QR Setup ---
QR_SETUP_ENABLED="true"
info "QR_SETUP_ENABLED=true — you can scan the QR code after deployment."

# ── Summary ───────────────────────────────────────────────────────────────────
header "Configuration Summary"

echo -e "  ${BOLD}Public IP:${NC}       $PUBLIC_IP"
echo -e "  ${BOLD}Domain:${NC}          $DOMAIN_NAME"
echo -e "  ${BOLD}Compose File:${NC}    $COMPOSE_FILE"
echo -e "  ${BOLD}ESL Password:${NC}    ${ESL_PASSWORD:0:4}****"
echo -e "  ${BOLD}DB Password:${NC}     ${DB_PASSWORD:0:4}****"
echo -e "  ${BOLD}Auth User:${NC}       $AUTH_USERNAME"
echo -e "  ${BOLD}Auth Password:${NC}   ******** (hashed)"
echo -e "  ${BOLD}TOTP Secret:${NC}     ${TOTP_SECRET:0:8}****"
echo -e "  ${BOLD}JWT Secret:${NC}      ${JWT_SECRET:0:8}****"
echo -e "  ${BOLD}Bypass Code:${NC}     ${EMERGENCY_BYPASS_CODE:0:8}****"
echo ""

read -p "$(echo -e "${BOLD}Proceed with deployment?${NC} [Y/n]: ")" CONFIRM
CONFIRM=${CONFIRM:-Y}
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    warn "Deployment cancelled."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: Generate .env
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 1/6 — Generating Environment File"

if [ -f ".env" ]; then
    warn "Existing .env found — backing up to .env.backup"
    cp .env .env.backup
fi

cat <<EOF > .env
# ═══════════════════════════════════════════════════════════════════════════════
# Broadcaster Production Environment
# Generated by install.sh on $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# ═══════════════════════════════════════════════════════════════════════════════

# ── Web & Domain ──────────────────────────────────────────────────────────────
DOMAIN_NAME=$DOMAIN_NAME

# ── Database ──────────────────────────────────────────────────────────────────
DB_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql+asyncpg://broadcaster:${DB_PASSWORD}@postgres/broadcaster
REDIS_URL=redis://redis:6379

# ── FreeSWITCH ESL ────────────────────────────────────────────────────────────
FS_ESL_PASSWORD=$ESL_PASSWORD
FS_ESL_HOST=freeswitch
FS_ESL_PORT=8021

# ── FreeSWITCH SIP (public-facing) ───────────────────────────────────────────
# This is the IP/domain agents use to register their softphones.
FS_SIP_DOMAIN=$PUBLIC_IP
FS_SIP_PORT=5060

# ── FreeSWITCH Media IP ──────────────────────────────────────────────────────
# CRITICAL: This IP goes into the SDP for all calls. PSTN carriers send
# RTP (voice + DTMF) to this address. Must be the VPS public IP.
EXT_RTP_IP=$PUBLIC_IP
EXT_SIP_IP=$PUBLIC_IP

# ── Authentication ────────────────────────────────────────────────────────────
AUTH_USERNAME=$AUTH_USERNAME
AUTH_PASSWORD_HASH=$AUTH_PASSWORD_HASH
TOTP_SECRET=$TOTP_SECRET
EMERGENCY_BYPASS_CODE=$EMERGENCY_BYPASS_CODE
JWT_SECRET=$JWT_SECRET
JWT_EXPIRE_HOURS=24
QR_SETUP_ENABLED=$QR_SETUP_ENABLED
EOF

success "Created .env with production values."

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Inject Public IP into FreeSWITCH Config
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 2/6 — Configuring FreeSWITCH Media IP"

VARS_FILE="freeswitch/conf/vars.xml"

if [ -f "$VARS_FILE" ]; then
    # Replace STUN lookups with the deterministic public IP.
    # This eliminates STUN latency at boot and ensures the correct IP is always used.
    if grep -q "external_rtp_ip=stun:stun.freeswitch.org" "$VARS_FILE"; then
        sed -i "s|external_rtp_ip=stun:stun.freeswitch.org|external_rtp_ip=${PUBLIC_IP}|g" "$VARS_FILE"
        success "Set external_rtp_ip=${PUBLIC_IP} in vars.xml"
    else
        info "external_rtp_ip already configured (not STUN default)."
    fi

    if grep -q "external_sip_ip=stun:stun.freeswitch.org" "$VARS_FILE"; then
        sed -i "s|external_sip_ip=stun:stun.freeswitch.org|external_sip_ip=${PUBLIC_IP}|g" "$VARS_FILE"
        success "Set external_sip_ip=${PUBLIC_IP} in vars.xml"
    else
        info "external_sip_ip already configured (not STUN default)."
    fi
else
    warn "vars.xml not found at ${VARS_FILE} — skipping. FreeSWITCH will use STUN."
fi

ESL_CONF_FILE="freeswitch/conf/autoload_configs/event_socket.conf.xml"
if [ -f "$ESL_CONF_FILE" ]; then
    if grep -q "<param name=\"password\"" "$ESL_CONF_FILE"; then
        sed -i -E "s|<param name=\"password\" value=\"[^\"]+\"/>|<param name=\"password\" value=\"${ESL_PASSWORD}\"/>|g" "$ESL_CONF_FILE"
        success "Injected ESL password into event_socket.conf.xml"
    fi
else
    warn "event_socket.conf.xml not found at ${ESL_CONF_FILE} — ESL password not set."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Configure Firewall
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 3/6 — Configuring Firewall"

# Install ufw if not present
if ! command -v ufw &> /dev/null; then
    info "Installing UFW..."
    apt-get update -qq && apt-get install -y -qq ufw > /dev/null 2>&1
fi

info "Configuring UFW rules..."

# Reset to defaults (deny incoming, allow outgoing)
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1

# SSH — always allow to avoid lockout
ufw allow 22/tcp comment "SSH" > /dev/null 2>&1
success "SSH (22/tcp)"

# HTTP / HTTPS — Caddy reverse proxy
ufw allow 80/tcp comment "HTTP - Caddy" > /dev/null 2>&1
ufw allow 443/tcp comment "HTTPS - Caddy" > /dev/null 2>&1
success "HTTP/HTTPS (80, 443/tcp)"

# SIP — FreeSWITCH external profile
ufw allow 5080/udp comment "FreeSWITCH SIP External" > /dev/null 2>&1
ufw allow 5080/tcp comment "FreeSWITCH SIP External TCP" > /dev/null 2>&1
success "SIP External (5080/udp+tcp)"

# SIP — FreeSWITCH internal profile (Agents/Softphones)
ufw allow 5060/udp comment "FreeSWITCH SIP Internal" > /dev/null 2>&1
ufw allow 5060/tcp comment "FreeSWITCH SIP Internal TCP" > /dev/null 2>&1
success "SIP Internal (5060/udp+tcp)"

# RTP — Voice media + DTMF (RFC 2833)
# This is the critical rule — without it, PSTN carriers can't send audio/DTMF back.
ufw allow 16384:32768/udp comment "FreeSWITCH RTP Media" > /dev/null 2>&1
success "RTP Media (16384-32768/udp)"

# Enable UFW non-interactively
ufw --force enable > /dev/null 2>&1
success "Firewall enabled and configured."

echo ""
info "Firewall rules:"
ufw status numbered 2>/dev/null | head -20

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Container Images
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 4/6 — Container Images"

if [ "$DEPLOY_METHOD" = "2" ]; then
    # Pull images from GHCR
    if grep -q "your-username" docker-compose.prod.yml; then
        sed -i "s/your-username/${GH_USER}/g" docker-compose.prod.yml
        success "Updated docker-compose.prod.yml with ghcr.io/${GH_USER}"
    fi

    # GHCR authentication
    echo ""
    info "If your container images are private, you need to log in to GHCR."
    read -p "$(echo -e "${BOLD}Log in to ghcr.io now?${NC} [Y/n]: ")" DO_LOGIN
    DO_LOGIN=${DO_LOGIN:-Y}

    if [[ "$DO_LOGIN" =~ ^[Yy]$ ]]; then
        echo ""
        info "You'll need a GitHub Personal Access Token (PAT) with read:packages scope."
        read -p "$(echo -e "${BOLD}GitHub PAT:${NC} ")" -s GH_TOKEN
        echo ""

        if [ -n "$GH_TOKEN" ]; then
            echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
            if [ $? -eq 0 ]; then
                success "Authenticated with ghcr.io"
            else
                error "Failed to authenticate."
            fi
        fi
    fi

    echo ""
    info "Pulling container images... (this may take a few minutes)"
    docker compose -f $COMPOSE_FILE pull
    success "All images pulled."
else
    # Build images locally
    echo ""
    info "Building images locally from source..."
    info "Depending on your VPS CPU, this will take 15-30 minutes."
    info "FreeSWITCH must compile from C++ source code."
    echo ""
    docker compose --profile full-stack -f $COMPOSE_FILE build
    success "All images built successfully."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: Start the Stack
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 5/6 — Starting Production Stack"

# Ensure no override file interferes
if [ -f "docker-compose.override.yml" ]; then
    warn "docker-compose.override.yml detected — this is a dev-only file."
    warn "Renaming to docker-compose.override.yml.dev to prevent interference."
    mv docker-compose.override.yml docker-compose.override.yml.dev
    success "Override file moved out of the way."
fi

info "Starting all services..."
if [ "$DEPLOY_METHOD" = "1" ]; then
    docker compose --profile full-stack -f $COMPOSE_FILE --env-file .env up -d
else
    docker compose -f $COMPOSE_FILE --env-file .env up -d
fi

echo ""
info "Waiting for services to initialize (30 seconds)..."
sleep 30

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6: Health Checks
# ═══════════════════════════════════════════════════════════════════════════════
header "Phase 6/6 — Health Checks"

if [ "$DEPLOY_METHOD" = "1" ]; then
    COMPOSE="docker compose --profile full-stack -f $COMPOSE_FILE"
else
    COMPOSE="docker compose -f $COMPOSE_FILE"
fi
ALL_HEALTHY=true

# Check each service
for svc in postgres redis caddy backend frontend freeswitch whisper-amd; do
    STATUS=$($COMPOSE ps --format '{{.Status}}' "$svc" 2>/dev/null | head -1)
    if echo "$STATUS" | grep -qi "up"; then
        success "$svc: $STATUS"
    else
        error "$svc: $STATUS (or not running)"
        ALL_HEALTHY=false
    fi
done

# FreeSWITCH-specific checks
echo ""
divider
info "FreeSWITCH module checks:"

FS_CONTAINER=$($COMPOSE ps -q freeswitch 2>/dev/null)
if [ -n "$FS_CONTAINER" ]; then
    # Check ext-rtp-ip
    FS_EXT_IP=$(docker exec "$FS_CONTAINER" fs_cli -p "$ESL_PASSWORD" -x 'eval $${external_rtp_ip}' 2>/dev/null || echo "UNKNOWN")
    if [ "$FS_EXT_IP" = "$PUBLIC_IP" ]; then
        success "external_rtp_ip = $FS_EXT_IP (matches VPS public IP)"
    else
        warn "external_rtp_ip = $FS_EXT_IP (expected $PUBLIC_IP)"
    fi

    # Check mod_spandsp
    SPANDSP=$(docker exec "$FS_CONTAINER" fs_cli -p "$ESL_PASSWORD" -x 'module_exists mod_spandsp' 2>/dev/null || echo "false")
    if [ "$SPANDSP" = "true" ]; then
        success "mod_spandsp loaded"
    else
        warn "mod_spandsp NOT loaded — in-band DTMF detection unavailable"
    fi

    # Check mod_amd
    AMD=$(docker exec "$FS_CONTAINER" fs_cli -p "$ESL_PASSWORD" -x 'module_exists mod_amd' 2>/dev/null || echo "false")
    if [ "$AMD" = "true" ]; then
        success "mod_amd loaded"
    else
        warn "mod_amd NOT loaded — AMD unavailable"
    fi

    # Check Sofia status
    SOFIA=$(docker exec "$FS_CONTAINER" fs_cli -p "$ESL_PASSWORD" -x 'sofia status' 2>/dev/null | grep -c "RUNNING" || true)
    SOFIA=${SOFIA:-0}
    if [ "$SOFIA" -gt 0 ]; then
        success "Sofia SIP profiles running ($SOFIA profiles)"
    else
        warn "No Sofia profiles running — check SIP configuration"
    fi
else
    error "FreeSWITCH container not found"
    ALL_HEALTHY=false
fi

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE
# ═══════════════════════════════════════════════════════════════════════════════
header "Deployment Complete"

if [ "$ALL_HEALTHY" = true ]; then
    echo -e "  ${GREEN}${BOLD}All services are running!${NC}\n"
else
    echo -e "  ${YELLOW}${BOLD}Some services may need attention — check warnings above.${NC}\n"
fi

echo -e "  ${BOLD}Web UI:${NC}          https://${DOMAIN_NAME}"
echo -e "  ${BOLD}API:${NC}             https://${DOMAIN_NAME}/api/v1"
echo -e "  ${BOLD}SIP Domain:${NC}      ${PUBLIC_IP}:5060"
echo -e "  ${BOLD}FreeSWITCH ESL:${NC}  localhost:8021 (password in .env)"
echo ""
divider
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo ""
echo -e "  View logs:      docker compose -f $COMPOSE_FILE logs -f"
echo -e "  Restart:        docker compose -f $COMPOSE_FILE restart"
echo -e "  Stop:           docker compose -f $COMPOSE_FILE down"
echo -e "  FS console:     docker exec -it \$(docker compose -f $COMPOSE_FILE ps -q freeswitch) fs_cli"
echo ""

if [ "$DOMAIN_NAME" != "$PUBLIC_IP" ]; then
    divider
    echo ""
    warn "Don't forget to create a DNS A record:"
    echo -e "    ${BOLD}${DOMAIN_NAME}${NC}  ->  ${BOLD}${PUBLIC_IP}${NC}"
    echo ""
    info "Caddy will auto-provision SSL once DNS propagates."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════════════
header "Authentication Credentials — SAVE THESE NOW"

echo -e "  ${RED}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "  ${RED}${BOLD}║  CRITICAL: Save these credentials before continuing!        ║${NC}"
echo -e "  ${RED}${BOLD}║  They will NOT be shown again.                              ║${NC}"
echo -e "  ${RED}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Username:${NC}             $AUTH_USERNAME"
echo -e "  ${BOLD}Password:${NC}             (the one you just entered)"
echo -e "  ${BOLD}TOTP Secret:${NC}          ${CYAN}$TOTP_SECRET${NC}"
echo -e "  ${BOLD}Emergency Bypass:${NC}     ${CYAN}$EMERGENCY_BYPASS_CODE${NC}"
echo -e "  ${BOLD}JWT Secret:${NC}           ${CYAN}$JWT_SECRET${NC}"
echo ""
divider
echo ""
echo -e "  ${BOLD}${GREEN}TOTP Setup Flow:${NC}"
echo -e "  1. Visit ${BOLD}https://${DOMAIN_NAME}/api/auth/qr${NC} in your browser"
echo -e "  2. Scan the QR code with Google Authenticator"
echo -e "  3. Edit .env and set ${BOLD}QR_SETUP_ENABLED=false${NC}"
echo -e "  4. Restart: ${BOLD}docker compose restart backend${NC}"
echo -e "  5. Login at ${BOLD}https://${DOMAIN_NAME}/login${NC}"
echo ""
echo -e "  ${YELLOW}If you lose your phone, use the Emergency Bypass Code${NC}"
echo -e "  ${YELLOW}as the TOTP field to log in. Change it after.${NC}"
echo ""

success "Deployment script finished."

