# Rule: Multi-Modal Document & Vector Storage

The memory-server supports storing and indexing ANY file type: Markdown, source code, text, PDFs, images (`.png`, `.jpg`, `.jpeg`, `.webp`), JSON, and tabular data.

## 1. Writing Files
- **Text & Code**: Send standard UTF-8 string in `content`:
  ```json
  {"path": "docs/architecture.md", "content": "# Architecture..."}
  ```
- **Binary Files (PDF, Images, Data)**: Base64-encode and send in `content_b64`:
  ```json
  {"path": "docs/spec.pdf", "content_b64": "<base64-string>"}
  ```

## 2. Automated Extraction and Vector Indexing
When any file is saved, the background indexer automatically:
- **PDFs**: Extracts text page-by-page using `pypdf`, indexing with `[docs/spec.pdf - Page X]` headers.
- **Images**: Extracts dimensions, format, mode, and EXIF metadata (plus sidecar `.txt`/`.md` captions) using `PIL.Image`.
- **Text/Code**: Chunks paragraphs into dense semantic chunks.
- Computes vector embeddings via Ollama (or falls back to GIN full-text index).

## 3. Reading Files
- Text files return `{"content": "...", "is_binary": false}`.
- Binary files return `{"content_b64": "...", "is_binary": true, "size": ...}`.
