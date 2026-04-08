from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.core import AgentStatus

class AgentBase(BaseModel):
    name: str
    phone_or_sip: str
    concurrent_cap: int = 1

class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    phone_or_sip: Optional[str] = None
    concurrent_cap: Optional[int] = None
    status: Optional[AgentStatus] = None

class AgentResponse(AgentBase):
    id: UUID
    status: AgentStatus
    current_calls: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
