# Pull Request: Robust RAG v2 & SharePoint Integration

This PR implements a comprehensive overhaul of the RAG pipeline to fix data retrieval biases, improve routing accuracy, and introduce automated data ingestion from SharePoint.

## 🚀 Key Features

### 1. Robust Data Ingestion
*   **SharePoint Automation Bridge**: Added `start_automation.ps1` and updated `main.py` to support real-time ingestion from Power Automate via ngrok.
*   **Flexible Upload Handler**: The `/upload` endpoint now intelligently handles:
    *   Multipart form data (Frontend uploads)
    *   JSON-wrapped base64 content (Power Automate)
    *   Raw binary streams
    *   *Fixes 400 Bad Request errors from Power Automate's variable header formats.*
*   **Expanded File Support**: Added native support for `.txt`, `.csv`, and `.md` files, with automatic fallback to PDF processing for unknown types.

### 2. Enhanced RAG Logic (`agent_manager.py`)
*   **Targeted Routing**: Level 1 routing now prioritizes `Title` matches (5x weight) over generic summaries, ensuring specific research reports (e.g., "Kenya Economic Strategy") are found.
*   **Smart Safety Net**: Implemented logic to SUPPRESS the semantic "Safety Net" when high-confidence documents are found. This stops the AI from hallucinating "Client Stories" when it should be reading a specific PDF.
*   **Massive Context Window**: Increased retrieval limit to **200,000 characters**, allowing the AI to read entire reports instead of small chunks.
*   **Clean Output Parsing**: Added regex filters to strip conversational fluff (e.g., "Here is the list...") from internal routing steps, preventing frontend crashes.

### 3. Infrastructure & Stability
*   **CORS Fix**: Updated `main.py` to allow cross-origin requests from all devices on the staging network.
*   **Data Restoration**: Included `import_qdrant_from_json.py` which successfully restored **6,500+ vector points**, fixing the "Empty Database" bug that was causing the original bias.
*   **Encoding Safety**: Patched test scripts to handle Windows terminal encoding (removed emojis that caused crashes).

## 🧪 Verification
*   **Search**: Confirmed accurate retrieval for "Kenya Economic Sectors" query (uses correct PDFs, no client stories).
*   **Ingestion**: Confirmed real-time indexing of files uploaded to SharePoint via Power Automate.
*   **Frontend**: Confirmed "API Query Undefined" error is resolved via stricter JSON parsing.

## 📦 Deployment
1.  Pull branch `feature/robust-rag-v2-final` on staging.
2.  Restart backend: `docker compose restart backend`.
3.  (Optional) Run `ngrok http 8000` to enable the SharePoint hook.
