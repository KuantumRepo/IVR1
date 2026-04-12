#!/bin/bash
set -e

echo "==========================================="
echo "  Broadcaster VPS Deployment Auto-Installer"
echo "==========================================="

# Check requirements
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose V2 is not installed."
    exit 1
fi

echo ""
read -p "Enter your public domain name for Web/API (e.g., app.domain.com): " DOMAIN_NAME
read -p "Enter your server's Public IP for SIP (e.g., 203.0.113.50): " PUBLIC_IP
read -p "Enter your GitHub Username or Org (where images are hosted): " GH_USER

if [ -f ".env" ]; then
    echo "⚠️ .env file already exists. Skipping password generation..."
else
    echo "🔒 Generating secure passwords and .env file..."
    
    # Generate secure random passwords (using /dev/urandom for wide compatibility)
    DB_PASSWORD=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 24 | head -n 1)
    ESL_PASSWORD=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 24 | head -n 1)
    
    cat <<EOF > .env
DOMAIN_NAME=$DOMAIN_NAME
DB_PASSWORD=$DB_PASSWORD
FS_ESL_PASSWORD=$ESL_PASSWORD
FS_SIP_DOMAIN=$PUBLIC_IP
FS_SIP_PORT=5060
# STUN fallbacks optionally overridable
EXT_SIP_IP=stun:stun.freeswitch.org
EXT_RTP_IP=stun:stun.freeswitch.org
EOF
    echo "✅ .env file created securely."
fi

# Replace placeholder username in docker-compose.prod.yml if it's there
if [ -f "docker-compose.prod.yml" ]; then
    sed -i "s/your-username/$GH_USER/g" docker-compose.prod.yml
    echo "✅ Updated docker-compose.prod.yml with GitHub Registry: ghcr.io/$GH_USER"
else
    echo "⚠️ WARNING: docker-compose.prod.yml not found in the current directory."
fi

echo ""
echo "🚀 Configuration complete!"
echo "-------------------------------------------"
echo "Next Steps:"
echo "1. If your images are private, authenticate Docker first:"
echo "   docker login ghcr.io -u $GH_USER"
echo ""
echo "2. Start the production stack:"
echo "   docker compose -f docker-compose.prod.yml --env-file .env up -d"
echo "==========================================="
