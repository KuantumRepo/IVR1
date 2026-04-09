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
