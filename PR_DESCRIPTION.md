# PR Description: Optimization of RAG Pipeline & Market Intelligence Extraction

## 👷 Technical Summary: Senior Review Request
This PR introduces enhancements to the Market Intelligence Tool's extraction layer and a comprehensive analysis of Adept Technologies' firmographic data. The changes focus on improving the precision of the RAG (Retrieval-Augmented Generation) pipeline and stabilizing the frontend-backend communication layer.

## 🛠 Key Technical Changes

### 1. RAG Pipeline Refinement (`Backend/agent_manager.py`)
- **Multi-Level Retrieval Logic:** Optimized the transition between Level 1 (Master Routing) and Level 3 (Detail Hydration).
- **Context Synthesis:** Improved the system prompt to enforce cross-referencing across multiple sources and strict inline citation formats.
- **Data Deduplication:** Refined keyword search weights (Title vs. Summary) to reduce redundant context injection.

### 2. Research Data Extraction (`Backend/extract_data.py`)
- **Direct Vector Store Mining:** Implemented a targeted extraction script to bypass high-level RAG noise and retrieve specific document chunks by ID/Metadata.
- **Memory Efficiency:** Optimized for reading large JSON dumps without full-memory saturation during data analysis phases.

### 3. Frontend Integration (`Front-end/Market-Intelligence/src/app/app.config.ts`)
- **API Connectivity:** Standardized service endpoints to resolve 404/URL mismatch issues encountered during cross-environment execution.

## 🔍 Areas for Senior Review
- **Concurrency Management:** Verify the `ThreadPoolExecutor` usage in `agent_manager.py` for Level 3 hydration; ensure thread-safe SQLite connections.
- **Prompt Engineering:** Review the updated instruction set in `_build_system_prompt` for potential "hallucination" risks when context is sparse.
- **Error Handling:** Check the `extract_data.py` error catching for robustness when parsing corrupted or non-standard JSON payloads.

## 📊 Business Intelligence Output
The research phase successfully documented:
- 5 specialized delivery pillars (CS, AI/ML, Cloud, SW Dev, E-Learning).
- Scale metrics (50M+ Data Points, 2M+ Interactions).
- Global compliance status (ISO 9001, ODPC Registry).

## ✅ Verification Steps
- [x] Verified `http://localhost:8000/query` endpoint for streaming responses.
- [x] Validated semantic search hit-rate for "Adept Teams/Sectors" query.
- [x] Confirmed Markdown citation rendering in the frontend.
