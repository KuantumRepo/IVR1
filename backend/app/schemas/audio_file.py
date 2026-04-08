from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class AudioFileResponse(BaseModel):
    id: UUID
    name: str
    original_name: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
