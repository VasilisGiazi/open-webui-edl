"""
All configuration is read from environment variables.
Copy .env.example → .env and fill in your values.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── This service ──────────────────────────────────────────────────────────
    api_key: str = ""  # Bearer token expected from Open-WebUI
    host: str = "0.0.0.0"
    port: int = 8081

    # ── Docling ───────────────────────────────────────────────────────────────
    docling_url: str = "http://docling:5001"
    docling_api_key: str = ""

    # Extra Docling params forwarded as-is (JSON string or empty)
    # e.g. '{"ocr_enabled": true}'
    docling_extra_params: str = ""

    # Docling request timeout in seconds. 0 = no timeout (matches Open-WebUI default).
    docling_timeout: int = 0

    # ── Storage backend ───────────────────────────────────────────────────────
    # Where to persist extracted images. One of: "azure", "local", "both".
    # "azure" → upload to Azure Blob Storage only (default, original behaviour)
    # "local" → write to a directory on disk only
    # "both"  → write to both; the markdown URL points at Azure (more durable)
    storage_backend: str = "azure"

    # ── Azure Blob Storage ────────────────────────────────────────────────────
    # Option A – connection string (simplest)
    azure_storage_connection_string: str = ""

    # Option B – account + key (alternative to connection string)
    azure_storage_account_name: str = ""
    azure_storage_account_key: str = ""

    # Container must exist and be set to "Blob (anonymous read access for blobs only)"
    azure_storage_container: str = "docling-images"

    # ── Local file storage ────────────────────────────────────────────────────
    # Filesystem path where images are written when storage_backend is "local"
    # or "both". Created on startup if it doesn't exist. In Docker, mount a
    # volume here so the files survive container restarts.
    local_storage_path: str = "/data/images"

    # Full URL prefix embedded in the returned markdown. The image filename
    # (<sha>.<ext>) is appended. Examples:
    #   http://docling-image-loader:8081/images   (inside the compose network)
    #   http://localhost:8081/images              (running as a local service)
    #   https://docs.example.com/images           (behind a reverse proxy)
    # Required when storage_backend is "local"; ignored otherwise.
    local_storage_url_prefix: str = ""


settings = Settings()
