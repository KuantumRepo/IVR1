from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.core import CampaignStatus, CampaignMode

class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    script_id: UUID
    max_concurrent_calls: int = 10
    calls_per_second: float = 1.0
    ring_timeout_sec: int = 30
    retry_attempts: int = 0
    retry_delay_min: int = 60

    enable_amd: bool = True
    hangup_on_voicemail: bool = True
    enable_vm_drop: bool = False
    use_legacy_dtmf: bool = False

    # AMD behavior mode: A (hangup on machine), B (VM drop after beep), C (conservative)
    campaign_mode: str = "A"
    # Audio file ID for voicemail drop (Mode B only)
    vm_drop_audio_id: Optional[UUID] = None

class CampaignCreate(CampaignBase):
    list_ids: List[UUID]
    gateway_ids: List[UUID]
    caller_id_ids: List[UUID] = []
    agent_ids: List[UUID] = []

class CampaignResponse(CampaignBase):
    id: UUID
    status: CampaignStatus
    total_contacts: int
    dialed_count: int
    answered_count: int
    transferred_count: int
    voicemail_count: int
    failed_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
