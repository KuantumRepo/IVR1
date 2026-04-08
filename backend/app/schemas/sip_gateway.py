from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.core import GatewayAuthType

class SipGatewayBase(BaseModel):
    name: str
    sip_server: str
    auth_type: GatewayAuthType = GatewayAuthType.PASSWORD
    sip_username: Optional[str] = None
    sip_password: Optional[str] = None
    max_concurrent: int = 30
    is_active: bool = True
    strip_plus: bool = False
    add_prefix: Optional[str] = None
    use_stir_shaken: bool = False
    transport: str = 'udp'
    settings_json: dict = {}

class SipGatewayCreate(SipGatewayBase):
    pass

class SipGatewayUpdate(SipGatewayBase):
    pass

class SipGatewayResponse(SipGatewayBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
