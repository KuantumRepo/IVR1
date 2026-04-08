from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class ContactBase(BaseModel):
    phone_number: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    is_dnc: bool = False

class ContactCreate(ContactBase):
    pass

class ContactResponse(ContactBase):
    id: UUID
    list_id: UUID
    model_config = ConfigDict(from_attributes=True)

class ContactListBase(BaseModel):
    name: str
    description: Optional[str] = None

class ContactListCreate(ContactListBase):
    pass

class ContactListResponse(ContactListBase):
    id: UUID
    total_contacts: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
