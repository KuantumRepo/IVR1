import logging
import re
import phonenumbers
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

from app.core.database import get_db
from app.models.core import ContactList, Contact
from app.schemas.contact import ContactListCreate, ContactListResponse, ContactCreate, ContactResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact-lists", tags=["Contacts"])


# ─── Phone Validation ─────────────────────────────────────────────────────────

def validate_phone(raw: str, default_region: str = "US") -> str | None:
    """
    Validate and normalize a phone number using Google's libphonenumber.

    Returns E.164-formatted string (e.g. '+15551234567') or cleaned digits.
    Falls back to raw digit validation for numbers that libphonenumber rejects
    but are still dialable via SIP (e.g. newly allocated ranges, test numbers).
    """
    raw = raw.strip()
    if not raw:
        return None

    # First pass: try libphonenumber for proper E.164 formatting
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    # Fallback: strip to digits and validate length
    # This catches numbers that libphonenumber rejects but are still dialable
    digits = re.sub(r'\D', '', raw)
    if len(digits) < 10 or len(digits) > 15:
        return None

    # Reject obviously garbage patterns (all same digit)
    if len(set(digits)) == 1:
        return None

    # Try one more time with cleaned digits
    try:
        parsed = phonenumbers.parse(f"+{digits}" if len(digits) > 10 else digits, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    # Accept as raw dialable number — prefix with + for E.164-ish format
    # For 10-digit US numbers, prepend country code
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+{digits}"
    else:
        return f"+{digits}"


# ─── List CRUD ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=ContactListResponse)
async def create_list(list_in: ContactListCreate, db: AsyncSession = Depends(get_db)):
    contact_list = ContactList(**list_in.model_dump())
    db.add(contact_list)
    await db.commit()
    await db.refresh(contact_list)
    return contact_list


@router.get("/", response_model=List[ContactListResponse])
async def get_lists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList).order_by(ContactList.created_at.desc()))
    return result.scalars().all()


@router.delete("/{list_id}")
async def delete_list(list_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="List not found")
    await db.delete(cl)
    await db.commit()
    return {"status": "deleted"}


# ─── Get Contacts in a List (paginated) ───────────────────────────────────────

@router.get("/{list_id}/contacts")
async def get_list_contacts(
    list_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Paginated retrieval of contacts within a specific list."""
    # Verify list exists
    list_result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = list_result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")

    # Total count
    count_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.list_id == list_id)
    )
    total = count_result.scalar() or 0

    # Paginated query
    offset = (page - 1) * per_page
    contacts_result = await db.execute(
        select(Contact)
        .where(Contact.list_id == list_id)
        .order_by(Contact.created_at.asc())
        .offset(offset)
        .limit(per_page)
    )
    contacts = contacts_result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "contacts": [
            {
                "id": str(c.id),
                "phone_number": c.phone_number,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in contacts
        ],
    }


# ─── CSV Upload ────────────────────────────────────────────────────────────────

@router.post("/{list_id}/upload-csv")
async def upload_contacts_csv(
    list_id: UUID,
    file: UploadFile = File(...),
    phone_col: str = Query("phone_number", description="CSV column name for phone number"),
    first_name_col: str = Query("first_name", description="CSV column name for first name"),
    last_name_col: str = Query("last_name", description="CSV column name for last name"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CSV file and import contacts into an existing list.

    Column mapping is done via query parameters so the frontend's mapping
    UI selections are actually respected. Defaults match the standard template.
    """
    # Validate list exists
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")

    # Parse CSV with pandas
    try:
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    # Validate phone column exists
    if phone_col not in df.columns:
        available = ", ".join(df.columns.tolist())
        raise HTTPException(
            status_code=400,
            detail=f"Phone column '{phone_col}' not found in CSV. Available columns: {available}"
        )

    # Get existing numbers in this list to prevent duplicates
    existing_res = await db.execute(
        select(Contact.phone_number).where(Contact.list_id == list_id)
    )
    seen_phones = set(existing_res.scalars().all())

    contacts_to_insert = []
    skipped_duplicate = 0
    skipped_invalid = 0
    total_in_file = len(df)

    for _, row in df.iterrows():
        raw_phone = str(row.get(phone_col, "")).strip()
        clean_phone = validate_phone(raw_phone)

        if not clean_phone:
            skipped_invalid += 1
            continue

        if clean_phone in seen_phones:
            skipped_duplicate += 1
            continue

        seen_phones.add(clean_phone)

        first_name = str(row.get(first_name_col, "")).strip() if first_name_col in df.columns else None
        last_name = str(row.get(last_name_col, "")).strip() if last_name_col in df.columns else None

        # Clean up pandas NaN → None
        if first_name and (first_name == "nan" or first_name == ""):
            first_name = None
        if last_name and (last_name == "nan" or last_name == ""):
            last_name = None

        contacts_to_insert.append(
            Contact(
                list_id=list_id,
                phone_number=clean_phone,
                first_name=first_name,
                last_name=last_name,
            )
        )

    # Bulk insert
    if contacts_to_insert:
        db.add_all(contacts_to_insert)

    # Reconcile total_contacts via actual COUNT(*) for accuracy
    await db.flush()
    count_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.list_id == list_id)
    )
    contact_list.total_contacts = count_result.scalar() or 0

    await db.commit()

    imported_count = len(contacts_to_insert)
    logger.info(
        f"CSV import to list {list_id}: {imported_count} imported, "
        f"{skipped_duplicate} duplicate, {skipped_invalid} invalid "
        f"(out of {total_in_file} rows)"
    )

    return {
        "status": "imported",
        "imported": imported_count,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "total_in_file": total_in_file,
    }


# ─── Paste Numbers (Bulk Quick-Add) ───────────────────────────────────────────

class PasteNumbersRequest(BaseModel):
    numbers: str  # Newline, comma, or semicolon separated phone numbers
    list_name: Optional[str] = None  # If set, creates a new list automatically


@router.post("/{list_id}/paste")
async def paste_numbers(
    list_id: UUID,
    payload: PasteNumbersRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk import phone numbers from pasted text.

    Accepts phone numbers separated by newlines, commas, semicolons, or
    whitespace. Validates each number with libphonenumber, deduplicates
    against existing contacts in the list, and inserts valid numbers.
    """
    # Validate list exists
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")

    # Split by common delimiters: newline, comma, semicolon, tab
    raw_numbers = re.split(r'[\n,;\t]+', payload.numbers)
    raw_numbers = [n.strip() for n in raw_numbers if n.strip()]

    if not raw_numbers:
        raise HTTPException(status_code=400, detail="No phone numbers provided")

    # Get existing numbers to dedup
    existing_res = await db.execute(
        select(Contact.phone_number).where(Contact.list_id == list_id)
    )
    seen_phones = set(existing_res.scalars().all())

    contacts_to_insert = []
    skipped_duplicate = 0
    skipped_invalid = 0

    for raw in raw_numbers:
        clean = validate_phone(raw)

        if not clean:
            skipped_invalid += 1
            continue

        if clean in seen_phones:
            skipped_duplicate += 1
            continue

        seen_phones.add(clean)
        contacts_to_insert.append(
            Contact(list_id=list_id, phone_number=clean)
        )

    if contacts_to_insert:
        db.add_all(contacts_to_insert)

    # Reconcile count
    await db.flush()
    count_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.list_id == list_id)
    )
    contact_list.total_contacts = count_result.scalar() or 0

    await db.commit()

    imported_count = len(contacts_to_insert)
    logger.info(
        f"Paste import to list {list_id}: {imported_count} imported, "
        f"{skipped_duplicate} duplicate, {skipped_invalid} invalid"
    )

    return {
        "status": "imported",
        "imported": imported_count,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "total_submitted": len(raw_numbers),
    }


# ─── Quick-Create List + Paste (one-shot) ─────────────────────────────────────

@router.post("/quick-import")
async def quick_import(
    payload: PasteNumbersRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new list and paste numbers in one shot.
    Convenience endpoint for the paste-numbers UI flow.
    """
    list_name = payload.list_name or "Quick Import"

    contact_list = ContactList(name=list_name)
    db.add(contact_list)
    await db.flush()  # get the ID

    # Split and validate
    raw_numbers = re.split(r'[\n,;\t]+', payload.numbers)
    raw_numbers = [n.strip() for n in raw_numbers if n.strip()]

    if not raw_numbers:
        raise HTTPException(status_code=400, detail="No phone numbers provided")

    seen_phones: set[str] = set()
    contacts_to_insert = []
    skipped_duplicate = 0
    skipped_invalid = 0

    for raw in raw_numbers:
        clean = validate_phone(raw)
        if not clean:
            skipped_invalid += 1
            continue
        if clean in seen_phones:
            skipped_duplicate += 1
            continue
        seen_phones.add(clean)
        contacts_to_insert.append(
            Contact(list_id=contact_list.id, phone_number=clean)
        )

    if contacts_to_insert:
        db.add_all(contacts_to_insert)

    contact_list.total_contacts = len(contacts_to_insert)
    await db.commit()
    await db.refresh(contact_list)

    return {
        "status": "imported",
        "list_id": str(contact_list.id),
        "list_name": contact_list.name,
        "imported": len(contacts_to_insert),
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "total_submitted": len(raw_numbers),
    }


# ─── Single Contact Add ───────────────────────────────────────────────────────

@router.post("/{list_id}/contacts", response_model=ContactResponse)
async def add_contact(list_id: UUID, contact_in: ContactCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactList).where(ContactList.id == list_id))
    contact_list = result.scalar_one_or_none()
    if not contact_list:
        raise HTTPException(status_code=404, detail="List not found")

    # Validate phone number
    clean_phone = validate_phone(contact_in.phone_number)
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    contact_data = contact_in.model_dump()
    contact_data["phone_number"] = clean_phone  # normalized E.164

    contact = Contact(list_id=list_id, **contact_data)
    db.add(contact)

    # Reconcile count
    await db.flush()
    count_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.list_id == list_id)
    )
    contact_list.total_contacts = count_result.scalar() or 0

    await db.commit()
    await db.refresh(contact)
    return contact
