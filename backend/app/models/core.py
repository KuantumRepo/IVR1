import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, DECIMAL, ForeignKey, Enum, Time, Table
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

# ENUMS
class CampaignStatus(str, enum.Enum):
    DRAFT = 'DRAFT'
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'
    COMPLETE = 'COMPLETE'
    ABORTED = 'ABORTED'

class CampaignType(str, enum.Enum):
    VOICE_BROADCAST = 'VOICE_BROADCAST'
    PRESS_ONE = 'PRESS_ONE'
    AUTO_DIAL = 'AUTO_DIAL'

class CallDisposition(str, enum.Enum):
    PENDING = 'PENDING'
    DIALING = 'DIALING'
    RINGING = 'RINGING'
    ANSWERED_HUMAN = 'ANSWERED_HUMAN'
    ANSWERED_MACHINE = 'ANSWERED_MACHINE'
    TRANSFERRED = 'TRANSFERRED'
    BUSY = 'BUSY'
    NO_ANSWER = 'NO_ANSWER'
    FAILED = 'FAILED'
    DNC = 'DNC'
    VOICEMAIL_DROPPED = 'VOICEMAIL_DROPPED'
    HANGUP = 'HANGUP'

class AgentStatus(str, enum.Enum):
    OFFLINE = 'OFFLINE'
    AVAILABLE = 'AVAILABLE'
    ON_CALL = 'ON_CALL'
    WRAP_UP = 'WRAP_UP'

class GatewayAuthType(str, enum.Enum):
    PASSWORD = 'PASSWORD'
    IP_BASED = 'IP_BASED'

class CampaignMode(str, enum.Enum):
    """AMD campaign behavior mode.
    A = MACHINE → hangup immediately (aggressive, saves SIP minutes)
    B = MACHINE → wait for beep → play VM drop audio → hangup (VM drop mode)
    C = UNKNOWN → assume human, continue IVR (conservative/agent-safe)
    """
    A = 'A'
    B = 'B'
    C = 'C'

class ScriptStepType(str, enum.Enum):
    AUDIO_FILE = 'AUDIO_FILE'
    TTS = 'TTS'

class IvrActionType(str, enum.Enum):
    TRANSFER = 'TRANSFER'
    HANGUP = 'HANGUP'
    GO_TO_NODE = 'GO_TO_NODE'
    DNC = 'DNC'

class IvrNodeType(str, enum.Enum):
    PROMPT = 'PROMPT'
    HANGUP = 'HANGUP'
    TRANSFER = 'TRANSFER'
    DNC = 'DNC'

# M2M Tables
campaign_contact_lists = Table(
    'campaign_contact_lists', Base.metadata,
    Column('campaign_id', UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="CASCADE"), primary_key=True),
    Column('list_id', UUID(as_uuid=True), ForeignKey('contact_lists.id', ondelete="CASCADE"), primary_key=True)
)

campaign_sip_gateways = Table(
    'campaign_sip_gateways', Base.metadata,
    Column('campaign_id', UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="CASCADE"), primary_key=True),
    Column('gateway_id', UUID(as_uuid=True), ForeignKey('sip_gateways.id', ondelete="CASCADE"), primary_key=True)
)

campaign_caller_ids = Table(
    'campaign_caller_ids', Base.metadata,
    Column('campaign_id', UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="CASCADE"), primary_key=True),
    Column('caller_id', UUID(as_uuid=True), ForeignKey('caller_ids.id', ondelete="CASCADE"), primary_key=True)
)

campaign_agents = Table(
    'campaign_agents', Base.metadata,
    Column('campaign_id', UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="CASCADE"), primary_key=True),
    Column('agent_id', UUID(as_uuid=True), ForeignKey('agents.id', ondelete="CASCADE"), primary_key=True)
)

# MODELS
class SipGateway(Base):
    __tablename__ = 'sip_gateways'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    sip_server = Column(String(500), nullable=False)
    auth_type = Column(Enum(GatewayAuthType), default=GatewayAuthType.PASSWORD, nullable=False)
    sip_username = Column(String(255))
    sip_password = Column(String(255))
    max_concurrent = Column(Integer, default=30, nullable=False)
    is_active = Column(Boolean, default=True)
    
    strip_plus = Column(Boolean, default=False)
    add_prefix = Column(String(20))
    use_stir_shaken = Column(Boolean, default=False)
    transport = Column(String(10), default='udp')
    settings_json = Column(JSONB, default=dict)
    
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class CallerId(Base):
    __tablename__ = 'caller_ids'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255))
    phone_number = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class AudioFile(Base):
    __tablename__ = 'audio_files'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    original_name = Column(String(500))
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer)
    duration_ms = Column(Integer)
    mime_type = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Agent(Base):
    __tablename__ = 'agents'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    
    # SIP registration — agent connects their softphone with these
    sip_extension = Column(String(50), unique=True, nullable=True)
    sip_password = Column(String(255), nullable=True)
    
    # Legacy / derived field (kept for backward compat in handlers)
    phone_or_sip = Column(String(500), nullable=False)
    
    concurrent_cap = Column(Integer, default=1, nullable=False)
    status = Column(Enum(AgentStatus), default=AgentStatus.OFFLINE)
    current_calls = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ContactList(Base):
    __tablename__ = 'contact_lists'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    total_contacts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    
    contacts = relationship("Contact", back_populates="contact_list", cascade="all, delete-orphan")

class Contact(Base):
    __tablename__ = 'contacts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id = Column(UUID(as_uuid=True), ForeignKey('contact_lists.id', ondelete="CASCADE"), nullable=False, index=True)
    phone_number = Column(String(30), nullable=False, index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    email = Column(String(255))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    country_code = Column(String(5), default='+1')
    misc_data_1 = Column(Text)
    misc_data_2 = Column(Text)
    misc_data_3 = Column(Text)
    extra = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    
    contact_list = relationship("ContactList", back_populates="contacts")

class CallScript(Base):
    __tablename__ = 'call_scripts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    script_type = Column(Enum(CampaignType), nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    
    nodes = relationship("IvrNode", back_populates="script", cascade="all, delete-orphan")

class IvrNode(Base):
    __tablename__ = 'ivr_nodes'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id = Column(UUID(as_uuid=True), ForeignKey('call_scripts.id', ondelete="CASCADE"), nullable=False, index=True)
    node_type = Column(Enum(IvrNodeType), default=IvrNodeType.PROMPT, nullable=False)
    name = Column(String(255))
    is_start_node = Column(Boolean, default=False)
    
    prompt_audio_id = Column(UUID(as_uuid=True), ForeignKey('audio_files.id', ondelete="SET NULL"))
    tts_text = Column(Text)
    tts_voice = Column(String(100), default='af_heart')
    
    script = relationship("CallScript", back_populates="nodes")
    routes = relationship("IvrRoute", foreign_keys="[IvrRoute.node_id]", back_populates="node", cascade="all, delete-orphan")

class IvrRoute(Base):
    __tablename__ = 'ivr_routes'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = Column(UUID(as_uuid=True), ForeignKey('ivr_nodes.id', ondelete="CASCADE"), nullable=False, index=True)
    
    key_pressed = Column(String(10), nullable=False) # e.g. '1', '2', '*', 'timeout'
    action_type = Column(Enum(IvrActionType), nullable=False)
    
    target_node_id = Column(UUID(as_uuid=True), ForeignKey('ivr_nodes.id', ondelete="SET NULL"), nullable=True)
    response_audio_id = Column(UUID(as_uuid=True), ForeignKey('audio_files.id', ondelete="SET NULL"), nullable=True)
    
    node = relationship("IvrNode", foreign_keys=[node_id], back_populates="routes")
    target_node = relationship("IvrNode", foreign_keys=[target_node_id])
    response_audio = relationship("AudioFile")

class Campaign(Base):
    __tablename__ = 'campaigns'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)
    script_id = Column(UUID(as_uuid=True), ForeignKey('call_scripts.id'), nullable=False)

    max_concurrent_calls = Column(Integer, default=10)
    calls_per_second = Column(DECIMAL(5,2), default=1.0)
    ring_timeout_sec = Column(Integer, default=30)
    retry_attempts = Column(Integer, default=0)
    retry_delay_min = Column(Integer, default=60)

    enable_amd = Column(Boolean, default=True)
    hangup_on_voicemail = Column(Boolean, default=True)
    enable_vm_drop = Column(Boolean, default=False)
    use_legacy_dtmf = Column(Boolean, default=False)

    # AMD campaign mode: A (hangup on machine), B (VM drop), C (conservative/assume human)
    campaign_mode = Column(Enum(CampaignMode), default=CampaignMode.A, nullable=False)
    # Audio file to play as a voicemail drop when Mode B detects beep
    vm_drop_audio_id = Column(UUID(as_uuid=True), ForeignKey('audio_files.id', ondelete="SET NULL"), nullable=True)
    # Per-campaign AMD tuning overrides (JSONB). When null, system defaults apply.
    # Example: {"initial_silence": 4000, "total_analysis_time": 6000, "short_speech_threshold_sec": 1.5}
    amd_config = Column(JSONB, nullable=True, default=None)

    total_contacts = Column(Integer, default=0)
    dialed_count = Column(Integer, default=0)
    answered_count = Column(Integer, default=0)
    transferred_count = Column(Integer, default=0)
    voicemail_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    contact_lists = relationship("ContactList", secondary=campaign_contact_lists)
    sip_gateways = relationship("SipGateway", secondary=campaign_sip_gateways)
    caller_ids = relationship("CallerId", secondary=campaign_caller_ids)
    agents = relationship("Agent", secondary=campaign_agents)
    script = relationship("CallScript")
    vm_drop_audio = relationship("AudioFile", foreign_keys=[vm_drop_audio_id])

class DialQueue(Base):
    __tablename__ = 'dial_queue'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id', ondelete="CASCADE"), nullable=False)
    phone_number = Column(String(30), nullable=False)
    
    priority = Column(Integer, default=50) # Higher goes first
    retry_count = Column(Integer, default=0)
    
    next_attempt_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    locked_by = Column(String(100), index=True)
    locked_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), default=utcnow)

class CallLog(Base):
    __tablename__ = 'call_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey('campaigns.id', ondelete="SET NULL"), nullable=True, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id', ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(30), nullable=False)
    
    duration = Column(Integer, default=0) # Total call duration in seconds
    hangup_cause = Column(String(255))
    amd_result = Column(String(50))

    # AMD telemetry — populated from channel variables set by amd_orchestrator.lua
    amd_layer = Column(String(20))         # 'mod_amd', 'whisper', or 'timeout'
    amd_decision_ms = Column(Integer)      # Milliseconds from answer to AMD decision
    amd_confidence = Column(DECIMAL(4,3))  # 0.000 – 1.000 confidence score
    amd_transcript = Column(Text)          # Whisper transcript (only if Layer 2 was used)
    
    timestamp = Column(DateTime(timezone=True), default=utcnow)
