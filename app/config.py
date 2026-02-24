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
    port: int = 8080

    # ── Docling ───────────────────────────────────────────────────────────────
    docling_url: str = "http://docling:5001"
    docling_api_key: str = ""

    # Extra Docling params forwarded as-is (JSON string or empty)
    # e.g. '{"ocr_enabled": true}'
    docling_extra_params: str = ""

    # Docling request timeout in seconds. 0 = no timeout (matches Open-WebUI default).
    docling_timeout: int = 0

    # Comma-separated file extensions to skip Docling processing (returned as-is).
    # e.g. ".txt,.html,.htm"
    skip_extensions: str = ".txt,.html,.htm"

    # ── Azure Blob Storage ────────────────────────────────────────────────────
    # Option A – connection string (simplest)
    azure_storage_connection_string: str = ""

    # Option B – account + key (alternative to connection string)
    azure_storage_account_name: str = ""
    azure_storage_account_key: str = ""

    # Container must exist and be set to "Blob (anonymous read access for blobs only)"
    azure_storage_container: str = "docling-images"


settings = Settings()
