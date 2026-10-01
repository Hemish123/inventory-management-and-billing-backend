"""
Storage helpers for photos (Azure Blob or local filesystem).

When AZURE_STORAGE_CONNECTION_STRING / ACCOUNT_NAME is set:
    - Uploads go to a PRIVATE Azure Blob container
    - URLs are short-lived SAS URLs (default 10 min expiry)

Otherwise:
    - Uploads go to MEDIA_ROOT/<subdir>/
    - URLs are standard Django MEDIA_URL paths
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger("passes")


def _strip_metadata(image_bytes: bytes) -> bytes:
    """
    Strip EXIF / metadata from an image for privacy.
    Returns re-encoded bytes (JPEG quality 92).
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        # Re-save without metadata
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue()
    except Exception:
        # If stripping fails, return original
        return image_bytes


def _generate_blob_name(prefix: str, ext: str = ".jpg") -> str:
    """Generate a unique blob name with date prefix."""
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    unique = uuid.uuid4().hex[:12]
    return f"{prefix}/{date_prefix}/{unique}{ext}"


# ───────────────────────────────────────────────
# Azure Blob Storage
# ───────────────────────────────────────────────
_blob_service_client = None
_blob_lock = __import__("threading").Lock()


def _get_blob_service():
    """Lazy-init Azure BlobServiceClient."""
    global _blob_service_client
    if _blob_service_client is None:
        with _blob_lock:
            if _blob_service_client is None:
                from azure.storage.blob import BlobServiceClient

                if settings.AZURE_STORAGE_CONNECTION_STRING:
                    _blob_service_client = BlobServiceClient.from_connection_string(
                        settings.AZURE_STORAGE_CONNECTION_STRING
                    )
                else:
                    from azure.storage.blob import BlobServiceClient as BSC

                    _blob_service_client = BSC(
                        account_url=f"https://{settings.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
                        credential=settings.AZURE_STORAGE_ACCOUNT_KEY,
                    )
                logger.info("Azure BlobServiceClient initialised")
    return _blob_service_client


def _upload_to_azure(blob_name: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Upload data to Azure Blob and return the blob name (path)."""
    from azure.storage.blob import ContentSettings

    client = _get_blob_service()
    container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)

    # Ensure container exists (no public access)
    try:
        container.get_container_properties()
    except Exception:
        container.create_container()

    blob_client = container.get_blob_client(blob_name)
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    logger.info("Uploaded blob: %s (%d bytes)", blob_name, len(data))
    return blob_name


def _get_azure_sas_url(blob_name: str) -> str:
    """Generate a short-lived SAS URL for a private blob."""
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    account_name = settings.AZURE_STORAGE_ACCOUNT_NAME
    account_key = settings.AZURE_STORAGE_ACCOUNT_KEY

    # If using connection string, parse the account name/key from it
    if not account_name and settings.AZURE_STORAGE_CONNECTION_STRING:
        parts = dict(
            item.split("=", 1)
            for item in settings.AZURE_STORAGE_CONNECTION_STRING.split(";")
            if "=" in item
        )
        account_name = parts.get("AccountName", "")
        account_key = parts.get("AccountKey", "")

    sas = generate_blob_sas(
        account_name=account_name,
        container_name=settings.AZURE_STORAGE_CONTAINER,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=settings.AZURE_SAS_EXPIRY_MINUTES),
    )
    return f"https://{account_name}.blob.core.windows.net/{settings.AZURE_STORAGE_CONTAINER}/{blob_name}?{sas}"


# ───────────────────────────────────────────────
# Local filesystem storage
# ───────────────────────────────────────────────
def _upload_to_local(blob_name: str, data: bytes) -> str:
    """Save data to MEDIA_ROOT and return the relative path."""
    full_path = Path(settings.MEDIA_ROOT) / blob_name
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)
    logger.info("Saved local file: %s (%d bytes)", full_path, len(data))
    return blob_name


def _get_local_url(blob_name: str) -> str:
    """Return the MEDIA_URL path for a local file."""
    return f"{settings.MEDIA_URL}{blob_name}"


# ───────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────
def upload_photo(image_bytes: bytes, prefix: str = "photos") -> str:
    """
    Strip metadata from image, upload to configured storage.

    Args:
        image_bytes: Raw image bytes
        prefix: Blob name prefix (e.g. "customer_photos", "pass_photos", "gate_scans")

    Returns:
        Blob name / relative path for storage in the database.
    """
    clean_bytes = _strip_metadata(image_bytes)
    blob_name = _generate_blob_name(prefix)

    if settings.USE_AZURE_STORAGE:
        return _upload_to_azure(blob_name, clean_bytes)
    else:
        return _upload_to_local(blob_name, clean_bytes)


def get_photo_url(blob_name: str) -> str:
    """
    Get a URL for a stored photo.
    Azure: short-lived SAS URL. Local: MEDIA_URL path.
    Returns empty string if blob_name is empty.
    """
    if not blob_name:
        return ""

    if settings.USE_AZURE_STORAGE:
        try:
            return _get_azure_sas_url(blob_name)
        except Exception as e:
            logger.warning("Failed to generate SAS URL for %s: %s", blob_name, e)
            return ""
    else:
        return _get_local_url(blob_name)
