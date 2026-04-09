Start Backend
cmd /c "cd backend && venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Start Frontend
pnpm dev    

# 🚨 PRODUCTION DEPLOYMENT WARNING 🚨
**FreeSWITCH Docker & STUN Networking**

Currently, `freeswitch/conf/vars.xml` uses the `stun-set` directive to dynamically resolve the external RTP and SIP IPs via `stun.freeswitch.org`. **This is perfectly fine for the local dev environment** (or environments where the container has unrestricted internet access and NAT pinholing works automatically).

**HOWEVER, FOR CLOUD/PRODUCTION DEPLOYMENTS:**
Multiple Docker FreeSWITCH projects explicitly warn that STUN **does not work reliably** inside Docker because of how Docker Bridge networks handle NAT topologies. In production (AWS, DigitalOcean, etc.), STUN may return the wrong IP, resulting in one-way audio or dropped calls.

**The Proper Production Solution:**
Before deploying to production, you MUST revisit the `stun-set` approach. The reliable, industry-standard solution is to use a **custom Docker entrypoint script** (`entrypoint.sh`) that reads your server's actual static public IP from an `.env` variable (or fetches it via a cloud metadata API), and natively injects or specifically `sed` replaces that real IP directly into the `vars.xml` config *before* the FreeSWITCH process starts.

---

# 🌐 Production Networking Topology (SIP vs HTTP)

When deploying via `docker-compose.yml`, please note that **Caddy ONLY proxies HTTP/HTTPS traffic**. Real-Time Communications (SIP/RTP) are UDP-based and bypass Caddy entirely, mapping directly from the host to the FreeSWITCH container.

```
┌─────────────────────────────────────────────────────────┐
│ Host Server (e.g. 203.0.113.50)                         │
│                                                         │
│   HTTPS (:443) ──►  [ Caddy ] ──► [ Frontend ]          │
│                               ──► [ Backend  ]          │
│                                                         │
│   UDP (:5060)  ──►  [ FreeSWITCH ]                      │
│   UDP (:16384+)──►                                      │
└─────────────────────────────────────────────────────────┘
```

Because of this split routing, you have two separate connection domains in `.env`:

1. `FS_ESL_HOST`: The internal host used by the Backend to send commands to FreeSWITCH. In Docker, this is `freeswitch`. In local dev without Docker, it's `127.0.0.1`.
2. `FS_SIP_DOMAIN`: The **public-facing** host that Agent Softphones use to register. Since agents are OUTSIDE the docker network, they cannot reach `freeswitch`. In production, this **MUST** be set to your public IP or A-record domain. Agent credentials presented in the UI rely on this variable.
