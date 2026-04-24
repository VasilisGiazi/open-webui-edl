"""
Image extraction and persistence.

Markdown produced by Docling with image_export_mode=embedded looks like:

    ![Description](data:image/png;base64,iVBORw0KGgo...)

This module:
1. Finds all such data-URI images with a regex
2. Computes SHA-256 of the raw bytes (content-addressed → natural dedup)
3. Persists the bytes via the configured backend(s):
   - "azure" → upload to Azure Blob Storage
   - "local" → write to a directory on disk (served by main.py at /images)
   - "both"  → write to both; the markdown URL points at Azure
4. Replaces the data-URI with the resulting URL
"""

import base64
import hashlib
import logging
import os
import re
from pathlib import Path

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

_VALID_BACKENDS = {"azure", "local", "both"}


def _backend() -> str:
    backend = settings.storage_backend.lower().strip()
    if backend not in _VALID_BACKENDS:
        raise RuntimeError(
            f"Invalid STORAGE_BACKEND={settings.storage_backend!r}. "
            f"Must be one of: {sorted(_VALID_BACKENDS)}"
        )
    return backend


# ─── Azure backend ────────────────────────────────────────────────────────────


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
    for part in settings.azure_storage_connection_string.split(";"):
        if part.startswith("AccountName="):
            return part[len("AccountName="):]
    raise RuntimeError(
        "Could not determine Azure Storage account name. "
        "Set AZURE_STORAGE_ACCOUNT_NAME or include it in AZURE_STORAGE_CONNECTION_STRING."
    )


def _build_azure_url(blob_name: str) -> str:
    account_name = _parse_account_name()
    container = settings.azure_storage_container
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"


def _save_to_azure(
    blob_service: BlobServiceClient,
    raw_bytes: bytes,
    blob_name: str,
) -> str:
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

    return _build_azure_url(blob_name)


# ─── Local backend ────────────────────────────────────────────────────────────


def _local_dir() -> Path:
    return Path(settings.local_storage_path)


def _local_url_prefix() -> str:
    prefix = settings.local_storage_url_prefix.strip()
    if not prefix:
        raise RuntimeError(
            "LOCAL_STORAGE_URL_PREFIX is required when STORAGE_BACKEND includes 'local'. "
            "Set it to the externally reachable URL prefix that Open-WebUI will use, "
            "e.g. http://docling-image-loader:8080/images"
        )
    return prefix.rstrip("/")


def _save_to_local(raw_bytes: bytes, file_name: str) -> str:
    target_dir = _local_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name

    if not target_path.exists():
        # Write atomically: tmp file in the same dir, then rename.
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        tmp_path.write_bytes(raw_bytes)
        os.replace(tmp_path, target_path)
        log.info("Wrote local image: %s (%d bytes)", target_path, len(raw_bytes))
    else:
        log.debug("Local image already exists, reusing: %s", target_path)

    return f"{_local_url_prefix()}/{file_name}"


# ─── Persistence orchestration ────────────────────────────────────────────────


def _persist_image(
    blob_service: BlobServiceClient | None,
    raw_bytes: bytes,
    mime_subtype: str,
) -> str:
    """
    Persist *raw_bytes* via the configured backend(s) and return the URL to
    embed in the markdown.

    For "both", we write to both backends and return the Azure URL (it's the
    more externally-reachable / durable one).
    """
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    ext = _MIME_TO_EXT.get(mime_subtype.lower(), mime_subtype.split("+")[0])
    file_name = f"{sha256}.{ext}"

    backend = _backend()
    azure_url: str | None = None
    local_url: str | None = None

    if backend in ("azure", "both"):
        assert blob_service is not None  # _get_blob_service_client() called upstream
        azure_url = _save_to_azure(blob_service, raw_bytes, file_name)

    if backend in ("local", "both"):
        try:
            local_url = _save_to_local(raw_bytes, file_name)
        except Exception:
            # If we already succeeded on Azure in "both" mode, don't lose that URL.
            if backend == "both" and azure_url:
                log.exception(
                    "Local write failed for %s but Azure upload succeeded — "
                    "using Azure URL.",
                    file_name,
                )
            else:
                raise

    # Choose the URL embedded in the markdown.
    if backend == "azure":
        return azure_url  # type: ignore[return-value]
    if backend == "local":
        return local_url  # type: ignore[return-value]
    # "both" → prefer Azure (external/durable), fall back to local if Azure failed.
    return azure_url or local_url  # type: ignore[return-value]


async def replace_images_with_urls(markdown: str) -> tuple[str, int]:
    """
    Find all embedded base64 images in *markdown*, persist each via the
    configured storage backend(s), and return (updated_markdown, image_count).
    """
    matches = list(_DATA_URI_RE.finditer(markdown))
    if not matches:
        return markdown, 0

    backend = _backend()

    # Only instantiate the Azure client when actually needed.
    blob_service = (
        _get_blob_service_client() if backend in ("azure", "both") else None
    )

    # Validate local config eagerly so we fail fast with a clear error.
    if backend in ("local", "both"):
        _ = _local_url_prefix()  # raises if missing
        _local_dir().mkdir(parents=True, exist_ok=True)

    # Cache sha256 → url within this document to avoid re-persisting identical
    # images that appear multiple times in the same file.
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
                url = _persist_image(blob_service, raw_bytes, mime_subtype)
                _cache[sha256] = url
            except Exception as exc:
                log.error(
                    "Failed to persist image %s: %s – keeping original",
                    sha256[:8],
                    exc,
                )
                return match.group(0)

        count += 1
        return f"![{alt_text}]({url})"

    updated_markdown = _DATA_URI_RE.sub(_replace, markdown)
    return updated_markdown, count


# Backwards-compatible alias for any external callers still using the old name.
replace_images_with_blob_urls = replace_images_with_urls
