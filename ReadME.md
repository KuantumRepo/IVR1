# Broadcaster — Voice Broadcasting & IVR Platform

High-volume voice broadcasting system with node-based IVR scripting, SIP agent management, and FreeSWITCH-powered call handling.

## Core Modules (All Working ✅)

| Module | Description |
|--------|-------------|
| **SIP Gateways** | Configure outbound SIP trunks for originating calls |
| **Caller IDs** | Manage outbound caller identity per campaign |
| **Agents** | Auto-provisioned SIP extensions with live registration diagnostics |
| **IVR Flow Builder** | Visual drag-and-drop node editor (PROMPT → TRANSFER / HANGUP / DNC) |
| **Audio Store** | Upload WAV files or generate TTS via Kokoro |
| **Test Simulator** | Live test calls with real-time trace logging |

## Quick Start (Development)

### Prerequisites
- Docker Desktop (FreeSWITCH, PostgreSQL, Redis)
- Python 3.12+ with venv
- Node.js 20+ with pnpm

### 1. Start Infrastructure
```bash
docker compose up -d
```
This starts FreeSWITCH, PostgreSQL, and Redis. First boot downloads ~90MB of sound packs.

### 2. Start Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start Frontend
```bash
cd frontend
pnpm install
pnpm dev
```

App runs at http://localhost:3000

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Docker Compose                                          │
│                                                          │
│  ┌─────────────┐  ┌──────────┐  ┌───────┐              │
│  │ FreeSWITCH  │  │ Postgres │  │ Redis │              │
│  │ :5060 (SIP) │  │ :5432    │  │ :6379 │              │
│  │ :8021 (ESL) │  └──────────┘  └───────┘              │
│  └──────┬──────┘                                        │
│         │ ESL (sendmsg + events)                        │
└─────────┼────────────────────────────────────────────────┘
          │
   ┌──────┴──────┐         ┌──────────────┐
   │   FastAPI   │◄────────│   Next.js    │
   │   Backend   │  API    │   Frontend   │
   │   :8000     │         │   :3000      │
   └─────────────┘         └──────────────┘
```

### Call Flow
```
Dialer → SIP Gateway → Prospect Phone
                              │ (answers)
                              ▼
                    FreeSWITCH (AMD check)
                              │
                              ▼
                    IVR Playback (TTS audio)
                              │ (DTMF press)
                              ▼
                    Route: TRANSFER / HANGUP / DNC
                              │
                              ▼ (if TRANSFER)
                    mod_callcenter queue
                              │
                              ▼
                    Agent Softphone (rings)
```

---

## Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Key Variables

| Variable | Dev Value | Prod Value | Purpose |
|----------|-----------|------------|---------|
| `FS_ESL_HOST` | `127.0.0.1` | `freeswitch` | Backend → FS management (internal) |
| `FS_SIP_DOMAIN` | `127.0.0.1` | Public IP / domain | Agent softphone registration (external) |
| `DATABASE_URL` | `...@127.0.0.1:5432/...` | `...@postgres/...` | PostgreSQL connection |
| `REDIS_URL` | `redis://127.0.0.1:6379` | `redis://redis:6379` | Redis connection |

---

## 🌐 Production Networking (SIP vs HTTP)

**Caddy ONLY proxies HTTP/HTTPS.** SIP and RTP are UDP-based and go directly to FreeSWITCH:

```
Internet
   │
   ├── HTTPS (:443)       ──► Caddy ──► Frontend / Backend
   │
   ├── SIP/UDP (:5060)    ──► FreeSWITCH (agent registration + call signaling)
   │
   └── RTP/UDP (:16384+)  ──► FreeSWITCH (voice media)
```

`FS_SIP_DOMAIN` **must** be set to your server's public IP or domain in production. Agent softphones connect directly to FreeSWITCH — they cannot resolve Docker-internal hostnames like `freeswitch`.

## 🚨 Production Deployment Notes

**FreeSWITCH STUN:** Currently uses `stun:stun.freeswitch.org` to discover the public IP. This works locally but is **unreliable in Docker on cloud servers**. For production, hardcode your public IP via `EXT_SIP_IP` and `EXT_RTP_IP` in the `.env`, or use a Docker entrypoint script that injects the IP before FreeSWITCH starts.

## Full-Stack Deployment

```bash
# Set production values
export FS_SIP_DOMAIN=203.0.113.50  # Your server's public IP
export EXT_SIP_IP=203.0.113.50
export EXT_RTP_IP=203.0.113.50

# Deploy everything
docker compose --profile full-stack up -d
```
