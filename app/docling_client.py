"""
Thin async wrapper around the Docling /v1/convert/file endpoint.
Requests image_export_mode=embedded so that images come back as
base64 data-URIs inside the markdown.
"""

import json
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


async def fetch_markdown_with_images(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
) -> str:
    """
    Send *file_bytes* to Docling and return the markdown string that
    contains embedded base64 images.
    """
    headers: dict[str, str] = {}
    if settings.docling_api_key:
        headers["X-Api-Key"] = settings.docling_api_key

    # Parse optional extra params
    extra_params: dict = {}
    if settings.docling_extra_params:
        try:
            extra_params = json.loads(settings.docling_extra_params)
        except json.JSONDecodeError:
            log.warning("DOCLING_EXTRA_PARAMS is not valid JSON – ignoring")

    docling_url = settings.docling_url.rstrip("/")

    # Match Open-WebUI behaviour: no timeout by default (large docs can take a long time)
    timeout = settings.docling_timeout if settings.docling_timeout > 0 else None

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{docling_url}/v1/convert/file",
            headers=headers,
            files={
                "files": (filename, file_bytes, mime_type),
            },
            data={
                # Key change vs. the default Open-WebUI loader:
                # "placeholder" → "embedded"  (gives us base64 images)
                "image_export_mode": "embedded",
                **extra_params,
            },
        )

    if not response.is_success:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(
            f"Docling returned HTTP {response.status_code}: {detail}"
        )

    result = response.json()
    md_content = result.get("document", {}).get("md_content", "")
    if not md_content:
        log.warning("Docling returned empty md_content")
    return md_content
