# 🔊 Broadcaster — Voice Broadcasting & Press-1 Live Transfer Platform

> *DandyDialer-inspired, self-hosted, BYO SIP trunk voice campaign system*

---

## 1. Project Vision

Build a self-hosted voice broadcasting platform that dials large lead lists in parallel, plays pre-recorded messages, detects voicemail/answering machines (auto-hangup), and when a live human presses **1**, instantly transfers them to an available agent. The system is **Bring-Your-Own-SIP** — users configure their own SIP trunks and allocate them freely across campaigns.

This is an **internal/personal tool** — no multi-tenancy, no billing, no compliance layer needed.

---

## 2. Technology Stack Decision

### 2.1 The Three Layers

```mermaid
graph TB
    subgraph "Layer 1 — Frontend (Next.js)"
        A[Admin Dashboard]
        B[Campaign Wizard]
        C[Real-Time Monitor]
        D[Analytics & Reports]
    end

    subgraph "Layer 2 — Backend API (Python / FastAPI)"
        E[REST API]
        F[WebSocket Server]
        G[Campaign Engine / Scheduler]
        H[CSV Importer]
        I[Audio Manager]
    end

    subgraph "Layer 3 — Telephony (FreeSWITCH)"
        J[SIP Gateway Bridge]
        K[Media Playback]
        L[DTMF Detection]
        M[AMD / Voicemail Detection]
        N[Call Bridge / Transfer]
    end

    subgraph "Data Layer"
        O[(PostgreSQL)]
        P[(Redis)]
        Q[File Storage - Audio/CSV]
    end

    A --> E
    B --> E
    C --> F
    E --> O
    E --> P
    G --> P
    G -->|ESL| J
    F -->|Events| G
    J --> K
    K --> L
    L --> N
    J --> M
```

### 2.2 Stack Justification

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | **Next.js 14 (App Router)** | React-based, SSR for fast loads, great DX, perfect for dashboard UIs. You already like it. |
| **Backend API** | **Python 3.12 + FastAPI** | Async-native, blazing fast, perfect for WebSockets. Python has the best FreeSWITCH ESL libraries. The campaign engine's concurrency model maps perfectly to Python's `asyncio`. |
| **Telephony Engine** | **FreeSWITCH** | Industry standard for high-volume outbound dialing. Handles 1000s of concurrent calls per node. Built-in AMD (`mod_amd`/`mod_avmd`), DTMF detection, call bridging. Controlled via ESL (Event Socket Library) from Python. |
| **Database** | **PostgreSQL 16** | Rock-solid relational DB. Partitioning for call logs, JSONB for flexible contact metadata, excellent indexing. |
| **Cache / Queue** | **Redis 7** | Campaign state machine, real-time call counters, pub/sub for live dashboard updates, job queue for dial tasks. |
| **File Storage** | **Local filesystem** (or S3-compatible later) | Audio files (mp3/wav/ogg), uploaded CSVs. Simple for a personal tool. |
| **TTS Engine** | **Kokoro TTS** | Open-weight 82M model. Deployed as a local Docker container for fast, high-quality, cost-free text-to-speech generation. |

### 2.3 Why NOT Node.js for Backend?

- FreeSWITCH ESL has **first-class Python support** (official `python-ESL` + community `greenswitch`/`switchio`)
- Node ESL wrappers are thin, poorly maintained, and miss edge cases
- Python's `asyncio` + FastAPI gives you the same async performance as Node but with much better telephony ecosystem support
- The campaign scheduling engine (rate limiting, retry logic, timezone awareness) is cleaner in Python

---

## 3. System Architecture — Detailed Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER'S BROWSER                               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Next.js Admin Dashboard                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │Campaigns │ │ Contacts │ │SIP Trunks│ │  Call Scripts  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │  Agents  │ │CallerIDs │ │Analytics │ │ Live Monitor  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  └────────────────────────┬─────────────────────────────────────┘   │
│                           │ HTTP + WebSocket                        │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                    BACKEND SERVER                                    │
│                           │                                          │
│  ┌────────────────────────▼─────────────────────────────────────┐   │
│  │              FastAPI Application Server                       │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │   │
│  │  │  REST API    │  │  WebSocket   │  │  Background Tasks │  │   │
│  │  │  (CRUD ops)  │  │  (live feed) │  │  (CSV import etc) │  │   │
│  │  └──────────────┘  └──────────────┘  └───────────────────┘  │   │
│  └────────────────────────┬─────────────────────────────────────┘   │
│                           │                                          │
│  ┌────────────────────────▼─────────────────────────────────────┐   │
│  │              Campaign Engine (Python asyncio)                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │ Dialer   │ │  Rate    │ │  Agent   │ │   Retry       │  │   │
│  │  │ Loop     │ │ Limiter  │ │ Tracker  │ │   Manager     │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  └────────────────────────┬─────────────────────────────────────┘   │
│                           │ ESL (Event Socket)                       │
│  ┌────────────────────────▼─────────────────────────────────────┐   │
│  │              FreeSWITCH                                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │mod_sofia │ │mod_dptools│ │ mod_amd  │ │mod_event_sock │  │   │
│  │  │(SIP)     │ │(playback)│ │(AMD/AVMD)│ │   (ESL)       │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │   PostgreSQL    │  │     Redis       │  │  File Storage       │ │
│  │   (persistent)  │  │  (state/queue)  │  │  (audio/csv)        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                            │
                     SIP (UDP/TCP)
                            │
              ┌─────────────▼──────────────┐
              │   External SIP Trunks      │
              │  (Telnyx, Twilio, VoIP.ms, │
              │   BulkVS, Voxbone, etc.)   │
              └────────────────────────────┘
                            │
                       PSTN / Phone Network
                            │
                    ┌───────▼───────┐
                    │  Lead Phones  │
                    └───────────────┘
```

---

## 4. Core Domain Model & Database Schema

### 4.1 Entity Relationship Diagram

```mermaid
erDiagram
    CAMPAIGNS ||--o{ CAMPAIGN_CONTACT_LISTS : has
    CAMPAIGNS ||--o{ CAMPAIGN_SIP_GATEWAYS : uses
    CAMPAIGNS ||--o{ CAMPAIGN_CALLER_IDS : uses
    CAMPAIGNS ||--o{ CAMPAIGNS_AGENTS : uses
    CAMPAIGNS ||--|| CALL_SCRIPTS : has

    CONTACT_LISTS ||--o{ CONTACTS : contains
    CONTACT_LISTS ||--o{ CAMPAIGN_CONTACT_LISTS : assigned_to

    SIP_GATEWAYS ||--o{ CAMPAIGN_SIP_GATEWAYS : assigned_to

    CALLER_IDS ||--o{ CAMPAIGN_CALLER_IDS : assigned_to

    AGENTS ||--o{ CAMPAIGNS_AGENTS : assigned_to

    CAMPAIGNS ||--o{ CALL_LOGS : generates
    CONTACTS ||--o{ CALL_LOGS : targeted_in
    AGENTS ||--o{ CALL_LOGS : handles
    SIP_GATEWAYS ||--o{ CALL_LOGS : routed_through

    CALL_SCRIPTS ||--o{ SCRIPT_STEPS : contains

    AUDIO_FILES ||--o{ SCRIPT_STEPS : used_in
```

### 4.2 Full PostgreSQL Schema

```sql
-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE campaign_status AS ENUM (
    'DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETE', 'ABORTED'
);

CREATE TYPE campaign_type AS ENUM (
    'VOICE_BROADCAST', 'PRESS_ONE', 'AUTO_DIAL'
);

CREATE TYPE call_disposition AS ENUM (
    'PENDING', 'DIALING', 'RINGING', 'ANSWERED_HUMAN',
    'ANSWERED_MACHINE', 'TRANSFERRED', 'BUSY', 'NO_ANSWER',
    'FAILED', 'DNC', 'VOICEMAIL_DROPPED', 'HANGUP'
);

CREATE TYPE agent_status AS ENUM (
    'OFFLINE', 'AVAILABLE', 'ON_CALL', 'WRAP_UP'
);

CREATE TYPE gateway_auth_type AS ENUM (
    'PASSWORD', 'IP_BASED'
);

CREATE TYPE script_step_type AS ENUM (
    'AUDIO_FILE', 'TTS'
);

-- ============================================================
-- CORE TABLES
-- ============================================================

-- SIP Gateways (BYO Trunk)
CREATE TABLE sip_gateways (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    sip_server      VARCHAR(500) NOT NULL,        -- e.g. trunk1.telnyx.com:5060
    auth_type       gateway_auth_type NOT NULL DEFAULT 'PASSWORD',
    sip_username    VARCHAR(255),
    sip_password    VARCHAR(255),
    max_concurrent  INT NOT NULL DEFAULT 30,
    is_active       BOOLEAN DEFAULT TRUE,
    -- Misc settings (like DandyDialer)
    strip_plus      BOOLEAN DEFAULT FALSE,        -- strip + from numbers
    add_prefix      VARCHAR(20),                  -- prepend prefix to dialed numbers
    use_stir_shaken BOOLEAN DEFAULT FALSE,
    transport       VARCHAR(10) DEFAULT 'udp',    -- udp/tcp/tls
    settings_json   JSONB DEFAULT '{}',           -- overflow config
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Caller IDs
CREATE TABLE caller_ids (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255),
    phone_number    VARCHAR(20) NOT NULL,          -- the DID number
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Audio Files
CREATE TABLE audio_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    original_name   VARCHAR(500),
    file_path       VARCHAR(1000) NOT NULL,        -- path on disk
    file_size       BIGINT,
    duration_ms     INT,                           -- duration in milliseconds
    mime_type       VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Agents
CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    phone_or_sip    VARCHAR(500) NOT NULL,          -- DID number or sip:user:pass@host
    concurrent_cap  INT NOT NULL DEFAULT 1,         -- max simultaneous calls
    status          agent_status DEFAULT 'OFFLINE',
    current_calls   INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Contact Lists
CREATE TABLE contact_lists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    total_contacts  INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts
CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id         UUID NOT NULL REFERENCES contact_lists(id) ON DELETE CASCADE,
    phone_number    VARCHAR(30) NOT NULL,
    first_name      VARCHAR(255),
    last_name       VARCHAR(255),
    email           VARCHAR(255),
    address         TEXT,
    city            VARCHAR(100),
    state           VARCHAR(50),
    zip_code        VARCHAR(20),
    country_code    VARCHAR(5) DEFAULT '+1',
    misc_data_1     TEXT,
    misc_data_2     TEXT,
    misc_data_3     TEXT,
    extra           JSONB DEFAULT '{}',             -- overflow CRM fields
    is_dnc          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    -- Index for fast lookup
    CONSTRAINT unique_phone_per_list UNIQUE (list_id, phone_number)
);

CREATE INDEX idx_contacts_phone ON contacts(phone_number);
CREATE INDEX idx_contacts_list ON contacts(list_id);

-- Call Scripts
CREATE TABLE call_scripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    script_type     campaign_type NOT NULL,
    -- Press-1 specific settings
    transfer_key    CHAR(1) DEFAULT '1',           -- DTMF key for transfer
    hangup_key      CHAR(1),                       -- optional DTMF key for hangup
    enable_hangup_response   BOOLEAN DEFAULT FALSE,
    enable_wrong_key_response BOOLEAN DEFAULT FALSE,
    -- Audio references for responses
    transfer_response_audio_id  UUID REFERENCES audio_files(id),
    hangup_response_audio_id    UUID REFERENCES audio_files(id),
    wrong_key_response_audio_id UUID REFERENCES audio_files(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Script Steps (playlist — ordered audio/TTS items)
CREATE TABLE script_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_id       UUID NOT NULL REFERENCES call_scripts(id) ON DELETE CASCADE,
    step_order      INT NOT NULL,
    step_type       script_step_type NOT NULL,
    audio_file_id   UUID REFERENCES audio_files(id),
    tts_text        TEXT,                           -- if TTS type
    tts_voice       VARCHAR(100) DEFAULT 'en-US-Standard-A',
    playlist_type   VARCHAR(20) DEFAULT 'default',  -- 'default' or 'voicemail'
    CONSTRAINT unique_step_order UNIQUE (script_id, step_order, playlist_type)
);

-- ============================================================
-- CAMPAIGNS (the central entity)
-- ============================================================
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    status          campaign_status DEFAULT 'DRAFT',
    script_id       UUID NOT NULL REFERENCES call_scripts(id),

    -- Dialing configuration
    max_concurrent_calls  INT DEFAULT 10,
    calls_per_second      DECIMAL(5,2) DEFAULT 1.0,   -- throttle rate
    ring_timeout_sec      INT DEFAULT 30,
    retry_attempts        INT DEFAULT 0,
    retry_delay_min       INT DEFAULT 60,

    -- Schedule
    call_window_start     TIME,                        -- e.g. 09:00
    call_window_end       TIME,                        -- e.g. 21:00
    timezone              VARCHAR(50) DEFAULT 'America/New_York',
    respect_local_tz      BOOLEAN DEFAULT FALSE,

    -- Voicemail detection
    enable_amd            BOOLEAN DEFAULT TRUE,
    hangup_on_voicemail   BOOLEAN DEFAULT TRUE,
    enable_vm_drop        BOOLEAN DEFAULT FALSE,

    -- DTMF settings
    use_legacy_dtmf       BOOLEAN DEFAULT FALSE,

    -- Stats (denormalized counters for speed)
    total_contacts        INT DEFAULT 0,
    dialed_count          INT DEFAULT 0,
    answered_count        INT DEFAULT 0,
    transferred_count     INT DEFAULT 0,
    voicemail_count       INT DEFAULT 0,
    failed_count          INT DEFAULT 0,

    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Junction tables (many-to-many)
CREATE TABLE campaign_contact_lists (
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    list_id         UUID REFERENCES contact_lists(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, list_id)
);

CREATE TABLE campaign_sip_gateways (
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    gateway_id      UUID REFERENCES sip_gateways(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, gateway_id)
);

CREATE TABLE campaign_caller_ids (
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    caller_id       UUID REFERENCES caller_ids(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, caller_id)
);

CREATE TABLE campaign_agents (
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    agent_id        UUID REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, agent_id)
);

-- ============================================================
-- CALL LOGS (high volume — partitioned by month)
-- ============================================================
CREATE TABLE call_logs (
    id              UUID DEFAULT gen_random_uuid(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id),
    contact_id      UUID REFERENCES contacts(id),
    agent_id        UUID REFERENCES agents(id),
    gateway_id      UUID REFERENCES sip_gateways(id),
    caller_id_used  VARCHAR(20),

    phone_number    VARCHAR(30) NOT NULL,
    disposition     call_disposition DEFAULT 'PENDING',
    dtmf_pressed    CHAR(1),

    -- FreeSWITCH data
    fs_uuid         VARCHAR(100),                    -- FreeSWITCH channel UUID
    hangup_cause    VARCHAR(100),
    sip_code        INT,

    -- Timing
    initiated_at    TIMESTAMPTZ DEFAULT NOW(),
    answered_at     TIMESTAMPTZ,
    transferred_at  TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    duration_sec    INT,
    billable_sec    INT,

    -- Retry tracking
    attempt_number  INT DEFAULT 1,

    PRIMARY KEY (id, initiated_at)
) PARTITION BY RANGE (initiated_at);

-- Create monthly partitions (example)
CREATE TABLE call_logs_2026_04 PARTITION OF call_logs
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE call_logs_2026_05 PARTITION OF call_logs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE INDEX idx_call_logs_campaign ON call_logs(campaign_id);
CREATE INDEX idx_call_logs_contact ON call_logs(contact_id);
CREATE INDEX idx_call_logs_disposition ON call_logs(disposition);

-- ============================================================
-- CAMPAIGN DIAL QUEUE (working table — what to dial next)
-- ============================================================
CREATE TABLE dial_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id),
    contact_id      UUID NOT NULL REFERENCES contacts(id),
    phone_number    VARCHAR(30) NOT NULL,
    priority        INT DEFAULT 0,                   -- higher = dial sooner
    attempt_count   INT DEFAULT 0,
    next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
    locked_by       VARCHAR(100),                    -- worker lock
    locked_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dial_queue_next ON dial_queue(campaign_id, next_attempt_at)
    WHERE locked_by IS NULL;
```

---

## 5. Call Flow — The Press-1 Engine

This is the heart of the system. Here's exactly what happens for each call:

```mermaid
flowchart TD
    A["Campaign Engine picks contact from dial_queue"] --> B["Originate call via ESL → FreeSWITCH"]
    B --> C{"Call Progress?"}

    C -->|"No Answer / Busy / Failed"| D["Log disposition → mark in dial_queue for retry or done"]
    C -->|"Answered"| E{"AMD Detection (mod_amd + mod_avmd)"}

    E -->|"Machine / Voicemail"| F{"VM Drop enabled?"}
    F -->|Yes| G["Play voicemail playlist → Hangup"]
    F -->|No| H["Hangup immediately"]

    E -->|"Human detected"| I["Play default playlist (audio/TTS steps)"]
    I --> J{"DTMF detected?"}

    J -->|"No key pressed"| K["Timeout → Hangup"]
    J -->|"Transfer key (1)"| L["Play transfer response audio"]
    J -->|"Hangup key"| M["Play hangup response → Hangup"]
    J -->|"Wrong key"| N["Play wrong key response → Replay prompt"]

    L --> O{"Find available agent"}
    O -->|"Agent available"| P["Bridge call to agent via SIP/PSTN"]
    O -->|"No agent free"| Q["Play 'please hold' → Queue until agent free"]

    P --> R["Call in progress: Agent ↔ Lead"]
    R --> S["Either party hangs up"]
    S --> T["Log full CDR: disposition=TRANSFERRED, duration, etc."]

    D --> U["Update campaign counters"]
    G --> U
    H --> U
    K --> U
    M --> U
    T --> U
    U --> V["Push real-time update via Redis Pub/Sub → WebSocket → Dashboard"]
```

### 5.1 ESL Integration Pattern (Python Side)

```python
# Pseudocode — Campaign Engine Dialer Loop

async def dial_contact(campaign, contact, gateway, caller_id):
    """Single outbound call via FreeSWITCH ESL"""

    # Build originate string using the BYO SIP trunk
    dial_string = (
        f"sofia/gateway/{gateway.name}/{contact.phone_number}"
    )

    originate_cmd = (
        f"originate {{{get_channel_vars(campaign, contact, caller_id)}}}"
        f"{dial_string} &park()"
    )

    # Send to FreeSWITCH
    result = await esl.bgapi(originate_cmd)
    call_uuid = parse_uuid(result)

    # Subscribe to events for this call
    await esl.filter("Unique-ID", call_uuid)

    # Event handler will take over from here
    return call_uuid


async def handle_call_event(event):
    """React to FreeSWITCH events for active calls"""

    event_name = event.get("Event-Name")
    uuid = event.get("Unique-ID")

    if event_name == "CHANNEL_ANSWER":
        # Start AMD detection
        await esl.execute("amd", "", uuid)

    elif event_name == "CUSTOM" and event.get("Event-Subclass") == "amd::info":
        amd_result = event.get("variable_amd_result")
        if amd_result == "MACHINE":
            await handle_voicemail(uuid)
        else:
            await play_script(uuid)

    elif event_name == "DTMF":
        digit = event.get("DTMF-Digit")
        await handle_keypress(uuid, digit)

    elif event_name == "CHANNEL_HANGUP":
        await finalize_call(uuid)
```

### 5.2 Agent Tracking (Redis)

```
# Real-time agent state in Redis (ultra-fast reads)
HSET agent:{agent_id} status "AVAILABLE"
HSET agent:{agent_id} current_calls 0
HSET agent:{agent_id} max_calls 1
HSET agent:{agent_id} last_call_at "2026-04-06T23:50:00Z"

# Campaign active calls counter
INCR campaign:{campaign_id}:active_calls
DECR campaign:{campaign_id}:active_calls

# Available agent lookup for transfer
SMEMBERS campaign:{campaign_id}:available_agents
```

---

## 6. Frontend — Next.js Admin Dashboard

### 6.1 Page Structure (DandyDialer-inspired)

```
/                           → Dashboard (overview of all campaigns)
/campaigns                  → Campaign list + quick controls (run/pause/abort)
/campaigns/create           → Campaign creation wizard (multi-step)
/campaigns/[id]             → Campaign detail + live monitor + analytics
/campaigns/[id]/analytics   → Deep analytics (conversion, funnel, duration)

/call-scripts               → List all call scripts
/call-scripts/create        → Call script designer (VB / Press-1 / Auto-dial)
/call-scripts/[id]/edit     → Edit script + playlist builder
/call-scripts/test          → Test call script wizard (select script, SIP gateway, Agent, Caller ID, rules)

/contacts                   → Contact lists overview
/contacts/[id]              → View contacts in list + CSV importer
/contacts/import            → CSV upload + column mapping wizard

/sip-gateways               → SIP trunk management
/sip-gateways/create        → Add new SIP gateway (server, auth, settings)
/sip-gateways/[id]/test     → Gateway test wizard

/agents                     → Agent management
/agents/create              → Add agent (phone/SIP, concurrent cap)

/caller-ids                 → Caller ID management

/audio                      → Audio file library (upload, preview, manage)

/settings                   → Global settings
```

### 6.2 Campaign Creation Wizard (3-Step, like DandyDialer)

```
Step 1: Basic Info
├── Campaign Name
├── Description
└── [Next]

Step 2: Resources (the key step)
├── Call Script      → Select existing or create new (inline wizard)
│   └── Script Type: Voice Broadcast | Press-1 | Auto-Dial
│       └── Playlist builder (audio files + TTS steps)
│       └── Key press handling (for Press-1)
│       └── Voicemail playlist (optional)
├── Contact Lists    → Select existing or upload new CSV
├── Caller IDs       → Select existing or add new
├── Agents           → Select existing or add new (Press-1/Auto-Dial only)
├── SIP Gateways     → Select existing or configure new
└── [Next]

Step 3: Campaign Options
├── Concurrent calls limit
├── Calls per second rate
├── Ring timeout
├── Call window hours (start/end time)
├── Timezone
├── AMD settings (enable, hangup on VM, VM drop)
├── Retry settings (attempts, delay)
├── Legacy DTMF toggle
└── [Create] or [Create & Run]
```

### 6.3 Real-Time Campaign Monitor

The live campaign view mirrors DandyDialer's approach:

```
┌──────────────────────────────────────────────────────────────┐
│  Campaign: "Solar Panel Leads Q2"        Status: ● ACTIVE   │
│  ════════════════════════════════════════════════════════════ │
│                                                              │
│  Progress: [████████████░░░░░░░░░░░░░░] 45%                │
│  Dialed: 4,500 / 10,000                                     │
│                                                              │
│  ┌─── Real-Time Call Graph (last 60 sec) ─────────────────┐ │
│  │  ▓▓▓ Active   ░░░ Ringing   ▒▒▒ Transferred           │ │
│  │                                                         │ │
│  │  30 ┤  ▓▓▓▓                                            │ │
│  │  20 ┤  ▓▓▓▓▓▓▓▓   ░░░                                 │ │
│  │  10 ┤  ▓▓▓▓▓▓▓▓▓▓▓░░░░░░ ▒▒▒                         │ │
│  │   0 ┼──────────────────────────────── time →            │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Quick Stats:                                                │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │Answered│ │Transfer│ │Voiceml │ │No Ansr │ │ Failed │   │
│  │  1,205 │ │   342  │ │   890  │ │  1,563 │ │   500  │   │
│  │  26.8% │ │  28.4% │ │  19.8% │ │  34.7% │ │  11.1% │   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
│                                                              │
│  [⏸ PAUSE]  [■ ABORT]  [✏ EDIT]  [📊 ANALYTICS]           │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 Tech Stack for Frontend

| Concern | Library |
|---------|---------|
| Framework | Next.js 14 (App Router) |
| State | Zustand (global) + TanStack Query (server state) |
| Real-time | Socket.IO client |
| Charts | Recharts or Apache ECharts |
| UI Components | shadcn/ui (Radix primitives + clean design) |
| Icons | Lucide React |
| Forms | React Hook Form + Zod validation |
| Table | TanStack Table |
| File upload | react-dropzone |
| Audio preview | Custom `<audio>` player component |
| CSV parsing | PapaParse (client-side preview) |
| Styling | Tailwind CSS (shadcn default) |

---

## 7. Backend API Design (FastAPI)

### 7.1 Service Layer Architecture

```
backend/
├── main.py                     # FastAPI app entry
├── core/
│   ├── config.py               # Settings (env-based)
│   ├── database.py             # SQLAlchemy async engine
│   ├── redis.py                # Redis connection pool
│   └── security.py             # Simple auth (API key or session)
├── api/
│   ├── v1/
│   │   ├── campaigns.py        # Campaign CRUD + control (run/pause/abort)
│   │   ├── call_scripts.py     # Script CRUD + step management
│   │   ├── contacts.py         # Contact list CRUD + CSV import
│   │   ├── sip_gateways.py     # Gateway CRUD + test
│   │   ├── agents.py           # Agent CRUD + status
│   │   ├── caller_ids.py       # Caller ID CRUD
│   │   ├── audio.py            # Audio file upload/download/preview
│   │   ├── analytics.py        # Campaign analytics queries
│   │   └── monitor.py          # WebSocket endpoint for live feed
│   └── deps.py                 # Dependency injection
├── models/                     # SQLAlchemy ORM models
│   ├── campaign.py
│   ├── contact.py
│   ├── call_script.py
│   ├── sip_gateway.py
│   ├── agent.py
│   ├── caller_id.py
│   ├── audio_file.py
│   └── call_log.py
├── schemas/                    # Pydantic request/response schemas
│   └── ...
├── engine/                     # THE CAMPAIGN ENGINE
│   ├── dialer.py               # Main dialer loop (asyncio)
│   ├── call_handler.py         # ESL event handler per call
│   ├── agent_tracker.py        # Agent availability (Redis-backed)
│   ├── rate_limiter.py         # CPS (calls per second) control
│   ├── retry_manager.py        # Retry logic
│   ├── amd_handler.py          # AMD result processor
│   └── gateway_manager.py      # Round-robin gateway selection
├── services/
│   ├── csv_importer.py         # Background CSV parsing
│   ├── tts_service.py          # Text-to-speech generation
│   └── audio_service.py        # Audio file processing (ffmpeg)
├── esl/
│   ├── connection.py           # FreeSWITCH ESL connection manager
│   ├── commands.py             # ESL command builders
│   └── events.py               # Event parser/dispatcher
└── workers/
    ├── campaign_worker.py      # Background campaign runner
    └── analytics_worker.py     # Periodic stats aggregation
```

### 7.2 Key API Endpoints

```
# Campaigns
POST   /api/v1/campaigns                    Create campaign
GET    /api/v1/campaigns                    List campaigns
GET    /api/v1/campaigns/{id}               Get campaign detail
PUT    /api/v1/campaigns/{id}               Update campaign
POST   /api/v1/campaigns/{id}/start         Start/Resume campaign
POST   /api/v1/campaigns/{id}/pause         Pause campaign
POST   /api/v1/campaigns/{id}/abort         Abort campaign
POST   /api/v1/campaigns/{id}/restart       Restart completed campaign
GET    /api/v1/campaigns/{id}/analytics     Get analytics data
WS     /api/v1/campaigns/{id}/live          WebSocket live feed

# Call Scripts
POST   /api/v1/call-scripts                Create script
GET    /api/v1/call-scripts                 List scripts
PUT    /api/v1/call-scripts/{id}            Update script
DELETE /api/v1/call-scripts/{id}            Delete script
POST   /api/v1/call-scripts/{id}/test       Test script
POST   /api/v1/call-scripts/{id}/steps      Add step to playlist

# Contacts
POST   /api/v1/contact-lists                Create list
POST   /api/v1/contact-lists/{id}/import    Upload & import CSV
GET    /api/v1/contact-lists/{id}/contacts  List contacts (paginated)

# SIP Gateways
POST   /api/v1/sip-gateways                Create gateway
GET    /api/v1/sip-gateways                 List gateways
POST   /api/v1/sip-gateways/{id}/test       Test gateway (make test call)

# Agents
POST   /api/v1/agents                       Create agent
GET    /api/v1/agents                        List agents (with live status)

# Caller IDs
POST   /api/v1/caller-ids                   Create caller ID
GET    /api/v1/caller-ids                    List caller IDs

# Audio
POST   /api/v1/audio/upload                 Upload audio file
GET    /api/v1/audio                         List audio files
GET    /api/v1/audio/{id}/stream             Stream audio for preview

# TTS
POST   /api/v1/tts/preview                  Generate TTS preview audio
```

---

## 8. FreeSWITCH Configuration

### 8.1 Deployment

FreeSWITCH runs as a **Docker container** on the same server or a dedicated VPS. Key configuration:

```xml
<!-- autoload_configs/event_socket.conf.xml -->
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="127.0.0.1"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="YOUR_SECURE_PASSWORD"/>
    <param name="apply-inbound-acl" value="loopback.auto"/>
  </settings>
</configuration>
```

### 8.2 Dynamic SIP Gateway Registration

When a user adds a SIP gateway in the dashboard, the Python backend dynamically registers it in FreeSWITCH via ESL:

```python
async def register_gateway(gateway: SipGateway):
    """Dynamically add a SIP gateway profile to FreeSWITCH"""
    xml_config = f"""
    <include>
      <gateway name="{gateway.id}">
        <param name="realm" value="{gateway.sip_server}"/>
        <param name="username" value="{gateway.sip_username}"/>
        <param name="password" value="{gateway.sip_password}"/>
        <param name="register" value="false"/>
        <param name="caller-id-in-from" value="true"/>
      </gateway>
    </include>
    """
    # Write to FreeSWITCH config and reload
    await esl.bgapi(f"sofia profile external rescan")
```

### 8.3 Key Modules Required

| Module | Purpose |
|--------|---------|
| `mod_sofia` | SIP stack — handles all SIP signaling |
| `mod_event_socket` | ESL — Python controls FreeSWITCH through this |
| `mod_dptools` | Dialplan tools — playback, bridge, transfer, park |
| `mod_amd` | Answering Machine Detection |
| `mod_avmd` | Advanced Voicemail Detection (beep detection) |
| `mod_tone_detect` | DTMF detection (in-band) |
| `mod_commands` | API commands |
| `mod_say` | TTS playback |
| `mod_sndfile` | Audio file format support (wav, mp3, ogg) |
| `mod_native_file` | Native file format support |
| `mod_shout` | MP3 streaming support |

---

## 9. Real-Time Data Pipeline

```mermaid
sequenceDiagram
    participant FS as FreeSWITCH
    participant Py as Python Engine
    participant RD as Redis
    participant WS as WebSocket Server
    participant UI as Next.js Dashboard

    FS->>Py: ESL Event (CHANNEL_ANSWER)
    Py->>RD: INCR campaign:123:active_calls
    Py->>RD: PUBLISH campaign:123:events {type: "ANSWER", ...}
    RD->>WS: Subscription notification
    WS->>UI: WebSocket message
    UI->>UI: Update live graph + counters

    FS->>Py: ESL Event (DTMF digit="1")
    Py->>Py: Bridge to available agent
    Py->>RD: SREM available_agents agent_456
    Py->>RD: PUBLISH campaign:123:events {type: "TRANSFER", ...}
    RD->>WS: Subscription notification
    WS->>UI: WebSocket message
    UI->>UI: Update transfer counter + agent status
```

---

## 10. Deployment Architecture

### 10.1 Single-Server Setup (Recommended for Personal Tool)

```
VPS / Dedicated Server (Linux)
├── Docker Compose
│   ├── freeswitch       (container)  — ports: 5060/udp, 5080/udp, 16384-32768/udp, 8021/tcp
│   ├── postgres         (container)  — port: 5432
│   ├── redis            (container)  — port: 6379
│   ├── kokoro-tts       (container)  — port: 8880
│   ├── backend          (container)  — Python/FastAPI — port: 8000
│   └── frontend         (container)  — Next.js — port: 3000
├── nginx (reverse proxy)             — port: 80/443 (SSL termination)
└── /data/
    ├── audio/           (uploaded audio files)
    ├── csv/             (uploaded CSVs)
    ├── postgres/        (DB volume)
    └── freeswitch/      (config volume)
```

### 10.2 Docker Compose Overview

```yaml
version: '3.8'

services:
  freeswitch:
    image: signalwire/freeswitch:latest
    network_mode: host           # Required for SIP/RTP
    volumes:
      - ./freeswitch/conf:/etc/freeswitch
      - ./data/audio:/audio
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: broadcaster
      POSTGRES_USER: broadcaster
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  kokoro-tts:
    image: ghcr.io/remsky/kokoro-fastapi-cpu:latest
    ports:
      - "8880:8880"
    restart: unless-stopped

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://broadcaster:${DB_PASSWORD}@postgres/broadcaster
      REDIS_URL: redis://redis:6379
      KOKORO_TTS_URL: http://kokoro-tts:8880
      FS_ESL_HOST: 127.0.0.1
      FS_ESL_PORT: 8021
      FS_ESL_PASSWORD: ${ESL_PASSWORD}
    volumes:
      - ./data/audio:/audio
      - ./data/csv:/csv
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000
      NEXT_PUBLIC_WS_URL: ws://backend:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped
```

---

## 11. Project Directory Structure

```
broadcaster/
├── PLAN/
│   └── architecture.md          ← (this file)
├── docker-compose.yml
├── .env
│
├── backend/                     ← Python / FastAPI
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/
│       ├── api/
│       ├── models/
│       ├── schemas/
│       ├── engine/
│       ├── services/
│       ├── esl/
│       └── workers/
│
├── frontend/                    ← Next.js 14
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── app/                 (App Router pages)
│       ├── components/          (UI components)
│       ├── lib/                 (API client, utils)
│       ├── hooks/               (custom React hooks)
│       └── stores/              (Zustand stores)
│
├── freeswitch/                  ← FreeSWITCH config
│   └── conf/
│       ├── autoload_configs/
│       ├── dialplan/
│       ├── directory/
│       └── sip_profiles/
│
└── data/                        ← Runtime data
    ├── audio/
    ├── csv/
    └── postgres/
```

---

## 12. Phased Implementation Roadmap

### Phase 1 — Foundation (Week 1-2)
- [ ] Set up Docker Compose (FreeSWITCH + Postgres + Redis)
- [ ] Initialize Next.js frontend with shadcn/ui
- [ ] Initialize FastAPI backend with database models
- [ ] Implement SIP Gateway CRUD + dynamic FreeSWITCH registration
- [ ] Implement basic ESL connection and test call

### Phase 2 — Core Resources (Week 2-3)
- [ ] Contact Lists: CRUD + CSV upload + column mapping wizard
- [ ] Audio Files: Upload, preview, manage
- [ ] Call Scripts: CRUD + playlist builder (audio + TTS steps)
- [ ] Agents: CRUD + status management
- [ ] Caller IDs: CRUD

### Phase 3 — Campaign Engine (Week 3-5)
- [ ] Campaign CRUD + creation wizard (3-step)
- [ ] Dial queue builder (populate from contact lists)
- [ ] Core dialer loop (async, rate-limited)
- [ ] AMD integration (mod_amd + mod_avmd)
- [ ] DTMF handling + Press-1 transfer logic
- [ ] Agent tracking + call bridging
- [ ] Voicemail detection + optional VM drop
- [ ] Campaign state machine (DRAFT → ACTIVE → PAUSED → COMPLETE)

### Phase 4 — Live Monitoring (Week 5-6)
- [ ] Redis pub/sub for real-time events
- [ ] WebSocket server in FastAPI
- [ ] Live campaign dashboard (real-time graph, counters)
- [ ] Campaign controls (pause/resume/abort) from UI

### Phase 5 — Analytics & Polish (Week 6-7)
- [ ] Campaign analytics (conversion ratio, funnel, call duration metrics)
- [ ] Hangup analysis
- [ ] Gateway test wizard
- [ ] Retry logic implementation
- [ ] Call window / timezone scheduling
- [ ] UI polish + dark mode

---

## 13. Key Design Decisions & Finalized Constraints

> [!IMPORTANT]
> ### Finalized Decisions
> 1. **Python + FastAPI** for backend (not Node.js) — better FreeSWITCH ESL ecosystem
> 2. **FreeSWITCH** over Asterisk — higher concurrency, better AMD, more scalable
> 3. **Single-server Docker Compose** — Deploying to a Linux VPS
> 4. **shadcn/ui + Tailwind** for frontend — clean, modern, DandyDialer-level polish
> 5. **No multi-tenancy / auth** — internal tool, single user
> 6. **TTS Engine** — Kokoro TTS (82M parameters, open-weight) will be used for high-quality, lightweight text-to-speech, deployed alongside the app via Docker.
> 7. **Agent Interface** — Simple external bridging: Agents will receive transferred calls on external SIP phones or direct PSTN numbers (configurable by admin). No web-based softphone required.
> 8. **Call Recording** — Not required. FreeSWITCH will not record the bridging sessions.
> 9. **Scale Target** — Initial target is up to 100 concurrent calls, fully configurable by the admin per campaign.
