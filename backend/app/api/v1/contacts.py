import pandas as pd
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.core import ContactList, Contact
from app.schemas.contact import ContactListCreate, ContactListResponse, ContactCreate, ContactResponse

router = APIRouter(prefix="/contact-lists", tags=["Contacts"])

@router.post("/", response_model=ContactListResponse)
async def create_list(list_in: ContactListCreate, db: AsyncSession = Depends(get_db)):
    contact_list = ContactList(**list_in.model_dump())
    db.add(contact_list)
    await db.commit()
    await db.refresh(contact_list)
    return contact_list

@router.get("/", response_model=List[ContactListResponse])
async def get_lists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList))
    return result.scalars().all()

@router.post("/{list_id}/upload-csv")
async def upload_contacts_csv(
    list_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")
        
    try:
        df = pd.read_csv(file.file)
        if 'phone_number' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must contain 'phone_number' column")
            
        # Get existing numbers in this list to prevent cross-batch duplication
        existing_res = await db.execute(select(Contact.phone_number).where(Contact.list_id == list_id))
        seen_phones = set(existing_res.scalars().all())
            
        contacts_to_insert = []
        for _, row in df.iterrows():
            raw_phone = str(row['phone_number']).strip()
            # E.164 strict numerical digest stripping parenthesis and whitespace
            clean_phone = re.sub(r'\D', '', raw_phone)
            
            if not clean_phone or clean_phone in seen_phones:
                continue
                
            seen_phones.add(clean_phone)
            contacts_to_insert.append(
                Contact(
                    list_id=list_id,
                    phone_number=clean_phone,
                    first_name=str(row.get('first_name', '')) if 'first_name' in df.columns else None,
                    last_name=str(row.get('last_name', '')) if 'last_name' in df.columns else None
                )
            )
            
        db.add_all(contacts_to_insert)
        contact_list.total_contacts += len(contacts_to_insert)
        await db.commit()
        return {"status": "imported", "count": len(contacts_to_insert)}
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{list_id}/contacts", response_model=ContactResponse)
async def add_contact(list_id: UUID, contact_in: ContactCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")
    
    contact = Contact(list_id=list_id, **contact_in.model_dump())
    db.add(contact)
    contact_list.total_contacts = (contact_list.total_contacts or 0) + 1
    await db.commit()
    await db.refresh(contact)
    return contact

@router.delete("/{list_id}")
async def delete_list(list_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="List not found")
    await db.delete(cl)
    await db.commit()
    return {"status": "deleted"}
