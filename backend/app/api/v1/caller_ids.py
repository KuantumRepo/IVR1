from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import CallerId
from app.schemas.caller_id import CallerIdCreate, CallerIdResponse

router = APIRouter(prefix="/caller-ids", tags=["Caller IDs"])

@router.post("/", response_model=CallerIdResponse)
async def create_caller_id(caller_id_in: CallerIdCreate, db: AsyncSession = Depends(get_db)):
    caller_id = CallerId(**caller_id_in.model_dump())
    db.add(caller_id)
    await db.commit()
    await db.refresh(caller_id)
    return caller_id

@router.get("/", response_model=List[CallerIdResponse])
async def list_caller_ids(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallerId))
    return result.scalars().all()

@router.delete("/{caller_id_id}")
async def delete_caller_id(caller_id_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallerId).where(CallerId.id == caller_id_id))
    cid = result.scalar_one_or_none()
    if not cid:
        raise HTTPException(status_code=404, detail="Caller ID not found")
        
    await db.delete(cid)
    await db.commit()
    return {"status": "deleted", "id": caller_id_id}
