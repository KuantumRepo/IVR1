from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

class CallerIdBase(BaseModel):
    name: str
    phone_number: str

class CallerIdCreate(CallerIdBase):
    pass

class CallerIdResponse(CallerIdBase):
    id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
