from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.core import AgentStatus

class AgentCreate(BaseModel):
    name: str
    sip_extension: str
    concurrent_cap: int = 1

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    sip_extension: Optional[str] = None
    concurrent_cap: Optional[int] = None
    status: Optional[AgentStatus] = None

class AgentResponse(BaseModel):
    id: UUID
    name: str
    sip_extension: Optional[str] = None
    phone_or_sip: str
    concurrent_cap: int
    status: AgentStatus
    current_calls: int
    sip_registered: bool = False
    sip_user_agent: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AgentCredentials(BaseModel):
    """Returned on creation — admin gives these to the agent."""
    sip_extension: str
    sip_password: str
    sip_server: str
    sip_port: int = 5060
