from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.core import CampaignType, IvrActionType

class IvrRouteBase(BaseModel):
    key_pressed: str
    action_type: IvrActionType
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
    is_start_node: bool = False
    prompt_audio_id: Optional[UUID] = None
    tts_text: Optional[str] = None
    tts_voice: str = "en-US-Standard-A"

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
