"""
AppraisAI — Supabase Storage Service
======================================
Handles uploading generated .docx reports to Supabase Storage
and generating signed download URLs.
"""

import os
import logging
from supabase import create_client

logger = logging.getLogger(__name__)

BUCKET = os.getenv("STORAGE_BUCKET", "appraisal-reports")


def get_storage():
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    return client.storage.from_(BUCKET)


async def upload_report(file_bytes: bytes, filename: str, folder: str = "drafts") -> str:
    """
    Upload a .docx file to Supabase Storage.

    Args:
        file_bytes: Raw bytes of the .docx file
        filename:   e.g. 'AppraisAI_Draft_APA-2026-1001_500_Smithfield.docx'
        folder:     Storage subfolder, e.g. 'drafts/{order_id}'

    Returns:
        The storage path (e.g. 'drafts/abc-123/AppraisAI_Draft_...')
        that can be used later to generate signed URLs.
    """
    storage = get_storage()
    storage_path = f"{folder}/{filename}"

    logger.info(f"Uploading report to storage: {storage_path}")

    storage.upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )

    logger.info(f"Upload complete: {storage_path}")
    return storage_path


def get_signed_url(storage_path: str, expires_in: int = 3600) -> str | None:
    """
    Generate a signed download URL for a stored report.

    Args:
        storage_path: The path returned by upload_report()
        expires_in:   Seconds until the URL expires (default 1 hour)

    Returns:
        Signed URL string, or None if generation fails.
    """
    if not storage_path:
        return None
    try:
        storage = get_storage()
        result = storage.create_signed_url(storage_path, expires_in)
        return result.get("signedURL") or result.get("signedUrl")
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {storage_path}: {e}")
        return None
