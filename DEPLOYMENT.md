# Broadcaster — Production Deployment Guide

## Overview

This guide walks you through deploying Broadcaster on a fresh Linux VPS.
The interactive `install.sh` script handles most of the work — this document
covers the prerequisites you need to complete **before** running it.

---

## Minimum Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| **OS** | Ubuntu 22.04 LTS / Debian 12 | Ubuntu 24.04 LTS |
| **RAM** | 4 GB | 8 GB |
| **CPU** | 2 vCPU | 4 vCPU |
| **Disk** | 40 GB SSD | 80 GB SSD |
| **Network** | Public IPv4 address | Static public IPv4 |

> **Important:** You need a VPS with a **public IPv4 address** and the ability to
> open UDP ports. Shared hosting and PaaS platforms (Heroku, Railway, etc.) will
> NOT work — VoIP requires direct UDP access on ports 5080 and 16384-32768.

### Tested Providers

- DigitalOcean (Droplets)
- Linode / Akamai
- Hetzner Cloud
- Vultr
- OVHcloud
- Any bare-metal or VPS with root access

---

## Step 1 — Provision Your VPS

Create a fresh Ubuntu 22.04+ server with your provider. Note down:

- **Public IP address** (e.g., `203.0.113.50`)
- **Root or sudo SSH access**

---

## Step 2 — SSH In and Install Docker

```bash
ssh root@YOUR_VPS_IP
```

Install Docker Engine and Docker Compose V2:

```bash
# Update packages
apt update && apt upgrade -y

# Install Docker using the official convenience script
curl -fsSL https://get.docker.com | sh

# Verify
docker --version
docker compose version
```

---

## Step 3 — Clone the Repository

```bash
cd /opt
git clone https://github.com/YOUR_USERNAME/broadcaster.git
cd broadcaster
```

> **Note:** If your repo is private, you'll need to authenticate with a
> [Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
> or deploy key first.

---

## Step 4 — Run the Install Script

```bash
chmod +x install.sh
./install.sh
```

The script is fully interactive — it will:

1. ✅ Detect your server's public IP automatically
2. ✅ Prompt for your domain name, GitHub registry, and other settings
3. ✅ Generate secure passwords and create the `.env` file
4. ✅ Inject the public IP into FreeSWITCH configuration
5. ✅ Configure the firewall (UFW) for SIP, RTP, HTTP, HTTPS, and SSH
6. ✅ Authenticate with your container registry (GHCR)
7. ✅ Pull all container images
8. ✅ Start the full production stack
9. ✅ Run health checks on all services

---

## Step 5 — DNS Configuration

After the script completes, point your domain to the VPS:

| Record | Name | Value |
|--------|------|-------|
| A | `app.yourdomain.com` | `YOUR_VPS_IP` |

Caddy will automatically provision an SSL certificate once DNS propagates (usually 1-5 minutes).

---

## Post-Deployment

### Verify the stack

```bash
docker compose -f docker-compose.prod.yml ps
```

All services should show `Up (healthy)` or `Up`.

### View logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f freeswitch
```

### Restart the stack

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

### Update to latest images

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## Architecture Diagram

```
                    Internet
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   HTTPS (443)    SIP (5080/udp)  RTP (16384-32768/udp)
        │              │              │
     ┌──▼──┐     ┌─────▼─────┐       │
     │Caddy│     │FreeSWITCH │◄──────┘
     │proxy│     │(host net) │
     └──┬──┘     └─────┬─────┘
        │              │ ESL (8021)
   ┌────┼────┐    ┌────▼────┐
   │    │    │    │ Backend │──► Whisper AMD
   │    │    │    │ (Python)│      (sidecar)
   ▼    ▼    │    └────┬────┘
┌────┐ ┌───┐ │         │
│Next│ │API│ │    ┌────▼────┐
│.js │ │   │ │    │Postgres │
└────┘ └───┘ │    │  Redis  │
             │    └─────────┘
             │
```

> FreeSWITCH runs with `network_mode: host` — it binds directly to the
> VPS public interface. All other services run on the Docker bridge network.
> The backend connects to FreeSWITCH via `host.docker.internal:8021` (ESL).

---

## Troubleshooting

### DTMF not working on PSTN calls

Verify the firewall allows inbound UDP on the RTP port range:

```bash
sudo ufw status | grep -i "16384:32768"
```

If missing, add the rule:

```bash
sudo ufw allow 16384:32768/udp comment "FreeSWITCH RTP"
```

### FreeSWITCH can't register with SIP provider

Check the external IP that FreeSWITCH is advertising:

```bash
docker exec broadcaster-freeswitch-1 fs_cli -x "eval \$\${external_rtp_ip}"
```

This must match your VPS public IP.

### Caddy fails to get SSL certificate

- Verify DNS A record points to the VPS IP
- Ensure ports 80 and 443 are open: `sudo ufw status`
- Check Caddy logs: `docker compose -f docker-compose.prod.yml logs caddy`
