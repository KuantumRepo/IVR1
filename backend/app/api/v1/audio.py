import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import AudioFile
from app.schemas.audio_file import AudioFileResponse

router = APIRouter(prefix="/audio", tags=["Audio Files"])

# Map to the Docker volume mount
UPLOAD_DIR = "/audio"

@router.post("/upload", response_model=AudioFileResponse)
async def upload_audio(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Depending on local vs docker run, we will just use a relative or absolute path.
    # In docker, /audio is bound. Locally, we might want to default to ./data/audio
    target_dir = UPLOAD_DIR if os.path.exists('/.dockerenv') else "./data/audio"
    os.makedirs(target_dir, exist_ok=True)
    
    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Must be an audio file")
        
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".wav"
    
    audio = AudioFile(
        name=name,
        original_name=file.filename,
        mime_type=file.content_type,
        file_path="" # Temporary
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)
    
    final_path = os.path.join(target_dir, f"{audio.id}{file_ext}")
    
    try:
        with open(final_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_size = os.path.getsize(final_path)
        audio.file_path = final_path
        audio.file_size = file_size
        await db.commit()
        await db.refresh(audio)
    except Exception as e:
        await db.delete(audio)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
        
    return audio

@router.get("/", response_model=List[AudioFileResponse])
async def list_audio_files(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioFile))
    return result.scalars().all()

@router.delete("/{audio_id}")
async def delete_audio(audio_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AudioFile).where(AudioFile.id == audio_id))
    audio = result.scalar_one_or_none()
    if not audio:
        raise HTTPException(status_code=404, detail="Audio file not found")
        
    if os.path.exists(audio.file_path):
        os.remove(audio.file_path)
        
    await db.delete(audio)
    await db.commit()
    return {"status": "deleted"}
