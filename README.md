# Docling Image Loader — Open-WebUI External Document Loader

> Extends Docling's markdown output by extracting embedded images,
> uploading them to **Azure Blob Storage**, and replacing inline base64
> data-URIs with permanent public URLs.

---

## Why does this exist?

The built-in Open-WebUI Docling loader uses `image_export_mode=placeholder`, so
images are stripped from the markdown.  
Switching to `embedded` mode inlines images as base64 data-URIs, which bloats
your vector database and can't be searched visually anyway.

This service sits between Open-WebUI and Docling:

```
Open-WebUI  ──PUT /process──►  docling-image-loader  ──POST /v1/convert/file──►  Docling
                                        │
                                        │  extract base64 images
                                        │  SHA-256 → deduplicated blob name
                                        ▼
                               Azure Blob Storage
                                        │
                                        │  public URL
                                        ▼
                               Markdown with ![alt](https://...)
```

---

## Quick Start

### 1 — Azure Blob Storage

1. Create a **Storage Account** in the Azure portal.
2. Create a **Container** (e.g. `docling-images`).
3. Set the container's **Public access level** to *Blob (anonymous read access for blobs only)*.
4. Copy the **Connection String** from
   *Storage account → Security + networking → Access keys*.

### 2 — Configure

```bash
cp .env.example .env
# Edit .env – fill in API_KEY, connection string, container name, etc.
```

### 3 — Run

```bash
docker compose up -d
```

This starts both Docling and the loader.  
If you already run Docling separately, edit `docker-compose.yml` to remove the
`docling` service and update `DOCLING_URL` to point at your instance.

### 4 — Configure Open-WebUI

In Open-WebUI:

| Setting | Value |
|---------|-------|
| Documents → Content Extraction Engine | **External** |
| External Document Loader URL | `http://docling-image-loader:8080` (or your host) |
| External Document Loader API Key | Same value as `API_KEY` in `.env` |

---

## How it works (code walkthrough)

| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI app, `PUT /process` endpoint |
| `app/config.py` | All config via env vars (pydantic-settings) |
| `app/docling_client.py` | Async HTTP call to Docling with `image_export_mode=embedded` |
| `app/image_processor.py` | Regex extraction → SHA-256 blob name → Azure upload → URL replacement |

### Image deduplication

Every image is named by its **SHA-256 hash** (e.g. `a3f9...d1.png`).
- The same image in two different documents is uploaded **once**.
- If the blob already exists the upload is skipped entirely.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEY` | ✓ | — | Bearer token checked on every request |
| `DOCLING_URL` | ✓ | `http://docling:5001` | Base URL of Docling |
| `DOCLING_API_KEY` | | `""` | Docling auth (if any) |
| `DOCLING_EXTRA_PARAMS` | | `""` | JSON string of extra Docling params |
| `DOCLING_TIMEOUT` | | `0` | Request timeout in seconds; `0` = no timeout |
| `AZURE_STORAGE_CONNECTION_STRING` | ✓* | — | Full connection string |
| `AZURE_STORAGE_ACCOUNT_NAME` | ✓* | — | Account name (Option B) |
| `AZURE_STORAGE_ACCOUNT_KEY` | ✓* | — | Account key (Option B) |
| `AZURE_STORAGE_CONTAINER` | ✓ | `docling-images` | Target container (must allow public blob access) |

*One of: connection string **or** (account name + key).

---

## Health check

```
GET /health  →  { "status": "ok" }
```

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # and fill in values
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
