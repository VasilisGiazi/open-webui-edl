"""
Image extraction & Azure Blob Storage upload.

Markdown produced by Docling with image_export_mode=embedded looks like:

    ![Description](data:image/png;base64,iVBORw0KGgo...)

This module:
1. Finds all such data-URI images with a regex
2. Computes SHA-256 of the raw bytes (content-addressed → natural dedup)
3. Uploads to Azure Blob Storage if the blob does not already exist
4. Replaces the data-URI with the public blob URL
"""

import base64
import hashlib
import logging
import re

from azure.storage.blob import BlobServiceClient

from app.config import settings

log = logging.getLogger(__name__)

# Matches:  ![alt text](data:image/TYPE;base64,DATA)
# Groups:   1=alt_text  2=mime_subtype  3=base64_data
_DATA_URI_RE = re.compile(
    r'!\[([^\]]*)\]\(data:image/([a-zA-Z0-9+.\-]+);base64,([A-Za-z0-9+/=\s]+?)\)',
    re.DOTALL,
)

# Typical extension map
_MIME_TO_EXT: dict[str, str] = {
    "png": "png",
    "jpeg": "jpg",
    "jpg": "jpg",
    "gif": "gif",
    "webp": "webp",
    "svg+xml": "svg",
    "tiff": "tiff",
    "bmp": "bmp",
}


def _get_blob_service_client() -> BlobServiceClient:
    if settings.azure_storage_connection_string:
        return BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )
    elif settings.azure_storage_account_name and settings.azure_storage_account_key:
        account_url = (
            f"https://{settings.azure_storage_account_name}.blob.core.windows.net"
        )
        return BlobServiceClient(
            account_url=account_url,
            credential=settings.azure_storage_account_key,
        )
    else:
        raise RuntimeError(
            "Azure Storage is not configured. Set either "
            "AZURE_STORAGE_CONNECTION_STRING or both "
            "AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY."
        )


def _parse_account_name() -> str:
    """Resolve account name from explicit setting or connection string."""
    if settings.azure_storage_account_name:
        return settings.azure_storage_account_name
    # Parse from connection string: ...;AccountName=foo;...
    for part in settings.azure_storage_connection_string.split(";"):
        if part.startswith("AccountName="):
            return part[len("AccountName="):]
    raise RuntimeError(
        "Could not determine Azure Storage account name. "
        "Set AZURE_STORAGE_ACCOUNT_NAME or include it in AZURE_STORAGE_CONNECTION_STRING."
    )


def _build_url(blob_name: str) -> str:
    account_name = _parse_account_name()
    container = settings.azure_storage_container
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"


def _upload_image(
    blob_service: BlobServiceClient,
    raw_bytes: bytes,
    mime_subtype: str,
) -> str:
    """
    Upload *raw_bytes* to Azure Blob Storage using its SHA-256 as the blob name.
    Returns the public (or SAS) URL.

    If the blob already exists it is NOT re-uploaded (idempotent / dedup).
    """
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    ext = _MIME_TO_EXT.get(mime_subtype.lower(), mime_subtype.split("+")[0])
    blob_name = f"{sha256}.{ext}"

    container_client = blob_service.get_container_client(
        settings.azure_storage_container
    )
    blob_client = container_client.get_blob_client(blob_name)

    if not blob_client.exists():
        blob_client.upload_blob(
            raw_bytes,
            blob_type="BlockBlob",
            overwrite=False,
        )
        log.info("Uploaded blob: %s (%d bytes)", blob_name, len(raw_bytes))
    else:
        log.debug("Blob already exists, reusing: %s", blob_name)

    return _build_url(blob_name)


async def replace_images_with_blob_urls(markdown: str) -> tuple[str, int]:
    """
    Find all embedded base64 images in *markdown*, upload each to Azure Blob
    Storage, and return (updated_markdown, image_count).
    """
    matches = list(_DATA_URI_RE.finditer(markdown))
    if not matches:
        return markdown, 0

    blob_service = _get_blob_service_client()

    # Cache sha256 → url within this document to avoid re-uploading identical
    # images that appear multiple times in the same file
    _cache: dict[str, str] = {}
    count = 0

    def _replace(match: re.Match) -> str:
        nonlocal count
        alt_text = match.group(1)
        mime_subtype = match.group(2)
        b64_data = match.group(3).replace("\n", "").replace(" ", "")

        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception as exc:
            log.warning("Could not decode base64 image: %s – keeping original", exc)
            return match.group(0)

        sha256 = hashlib.sha256(raw_bytes).hexdigest()

        if sha256 in _cache:
            url = _cache[sha256]
        else:
            try:
                url = _upload_image(blob_service, raw_bytes, mime_subtype)
                _cache[sha256] = url
            except Exception as exc:
                log.error("Failed to upload image %s: %s – keeping original", sha256[:8], exc)
                return match.group(0)

        count += 1
        return f"![{alt_text}]({url})"

    updated_markdown = _DATA_URI_RE.sub(_replace, markdown)
    return updated_markdown, count
