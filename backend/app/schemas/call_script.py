from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.core import CampaignType, IvrNodeType 

class IvrRouteBase(BaseModel):
    key_pressed: str
    target_node_id: Optional[UUID] = None
    response_audio_id: Optional[UUID] = None

class IvrRouteCreate(IvrRouteBase):
    pass

class IvrRouteResponse(IvrRouteBase):
    id: UUID
    node_id: UUID
    model_config = ConfigDict(from_attributes=True)

class IvrNodeBase(BaseModel):
    name: Optional[str] = None
    node_type: IvrNodeType = IvrNodeType.PROMPT
    is_start_node: bool = False
    prompt_audio_id: Optional[UUID] = None
    tts_text: Optional[str] = None
    tts_voice: Optional[str] = "af_heart"

class IvrNodeCreate(IvrNodeBase):
    id: Optional[UUID] = None
    routes: List[IvrRouteCreate] = []

class IvrNodeResponse(IvrNodeBase):
    id: UUID
    script_id: UUID
    routes: List[IvrRouteResponse] = []
    model_config = ConfigDict(from_attributes=True)

class CallScriptBase(BaseModel):
    name: str
    description: Optional[str] = None
    script_type: CampaignType

class CallScriptCreate(CallScriptBase):
    nodes: List[IvrNodeCreate] = []

class CallScriptResponse(CallScriptBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    nodes: List[IvrNodeResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class TestCallRequest(BaseModel):
    phone_number: str
    script_id: UUID
    gateway_id: Optional[UUID] = None
    caller_id_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    enable_amd: bool = True
    campaign_mode: str = "A"
    vm_drop_audio_id: Optional[UUID] = None
