"""
AppraisAI — Supabase Storage Service
======================================
Handles uploading generated .docx reports and client-uploaded documents
to Supabase Storage, and generating signed download URLs.
"""

import os
import logging
from supabase import create_client

logger = logging.getLogger(__name__)

BUCKET = os.getenv("STORAGE_BUCKET", "appraisal-reports")
DOCS_BUCKET = os.getenv("DOCS_BUCKET", "order-documents")


def get_storage_client():
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


def get_storage(bucket: str = BUCKET):
    return get_storage_client().storage.from_(bucket)


async def upload_report(file_bytes: bytes, filename: str, folder: str = "drafts") -> str:
    """
    Upload a .docx report to Supabase Storage.
    Returns the storage path (e.g. 'drafts/abc-123/AppraisAI_Draft_...').
    """
    storage = get_storage(BUCKET)
    path = f"{folder}/{filename}"
    try:
        storage.upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        )
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            storage.update(
                path=path,
                file=file_bytes,
                file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            )
        else:
            raise
    return path


async def get_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """Generate a signed download URL for a stored report."""
    storage = get_storage(BUCKET)
    result = storage.create_signed_url(storage_path, expires_in)
    return result.get("signedURL", "")


async def upload_order_document(
    file_bytes: bytes,
    filename: str,
    order_id: str,
    doc_type: str = "general"
) -> str:
    """
    Upload a client-provided document (income statement, expense doc, etc.)
    to Supabase Storage under order-documents/{order_id}/{doc_type}/{filename}.

    Args:
        file_bytes: Raw bytes of the uploaded file
        filename:   Original filename (e.g. 'rent_roll.xlsx')
        order_id:   UUID of the order
        doc_type:   'income', 'expenses', or 'general'

    Returns:
        The storage path, e.g. 'APA-2026-1001/income/rent_roll.xlsx'
    """
    storage = get_storage(DOCS_BUCKET)
    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    path = f"{order_id}/{doc_type}/{safe_name}"

    # Guess content type
    fname_lower = filename.lower()
    if fname_lower.endswith(".pdf"):
        ct = "application/pdf"
    elif fname_lower.endswith(".docx"):
        ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fname_lower.endswith((".xlsx", ".xls")):
        ct = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        ct = "application/octet-stream"

    try:
        storage.upload(path=path, file=file_bytes, file_options={"content-type": ct})
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            storage.update(path=path, file=file_bytes, file_options={"content-type": ct})
        else:
            raise
    logger.info(f"Uploaded order document: {path}")
    return path


async def download_file_bytes(storage_path: str, bucket: str = DOCS_BUCKET) -> bytes:
    """Download a file from Supabase Storage and return raw bytes."""
    storage = get_storage(bucket)
    response = storage.download(storage_path)
    return response
