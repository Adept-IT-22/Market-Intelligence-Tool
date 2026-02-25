# 🇰🇪 Market Intelligence Tool

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Angular](https://img.shields.io/badge/angular-19-red.svg)
![Groq/Gemini](https://img.shields.io/badge/inference-Groq%2FGemini-blueviolet.svg)
![Qdrant](https://img.shields.io/badge/vector--db-Qdrant-green.svg)

A high-performance, AI-driven analytics platform designed to provide deep insights into the Kenyan market. Leveraging cutting-edge LLM inference and an optimized Retrieval Augmented Generation (RAG) pipeline, this tool delivers precise, data-backed answers with extreme responsiveness.

---

## ✨ Key Features & Performance Wins

### ⚡ Lightning-Fast Performance
- **Dual-Layer Query Caching**: 
  - **L1 (Browser)**: Persistent LocalStorage cache for instant repeat-query results (0ms).
  - **L2 (Server)**: SQLite-backed semantic cache with 24h TTL and integrated error guards.
- **Parallel Retrieval Engine**: Concurrent execution of SQL relational data fetching and Qdrant vector search using `ThreadPoolExecutor`, reducing total latency by ~40%.
- **Streaming Response Architecture**: Backend-ready support for Server-Sent Events (SSE) for real-time token generation.
- **Sub-Second Logic Execution**: Optimized for high-throughput inference using Groq and Gemini-2.0-Flash.

### 🧠 Deep Market Intelligence
- **Geographic HQ Context**: Hardcoded headquarters context (Nairobi, Kenya) in the system prompt ensures the AI correctly distinguishes between "local" (Kenya) and "abroad" (international).
- **Hybrid Retrieval Logic**: A sophisticated 3-level filtering system:
  1. **Master Routing**: High-level semantic + keyword search across document routing tables.
  2. **Vector Hydration**: Dynamic resolution of SQL pointers to full-text payloads in Qdrant.
  3. **Context Synthesis**: Multi-source grounding with mandatory markdown citation requirements.
- **Automated Ingestion**: Seamless remote file ingestion from SharePoint via **Power Automate** + **ngrok**, with localized department/source tracking.

### 🎨 Premium UI/UX
- **Threaded Conversation Tree**: Visual history with threaded connectors linking queries and responses.
- **GSAP Micro-Animations**: Professional typewriter effects and dynamic state-based loading indicators (Scanning, Synthesizing...).
- **Glassmorphism Design**: Sleek, modern aesthetics with backdrop-blur effects and responsive layouts.
- **Theme Parity**: Native Dark/Light mode support managed via Angular Signals.

---

## 🛠️ Tech Stack

- **Frontend**: Angular 19 (Static Mode), Angular Material.
- **Backend**: Flask (Python), Gemini/Groq SDKs.
- **Vector DB**: Qdrant (Port 7000).
- **RDBMS**: SQLite (Structured data, chat history, and caching).
- **Embeddings**: `sentence-transformers` (BAAI/bge-small-en).

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ | Node.js & npm | Qdrant Server

### 2. Rapid Installation
```bash
# Backend
cd Backend
python -m venv venv
# Windows: .\venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python main.py

# Frontend
cd Front-end/Market-Intelligence
npm install
npm start
```

### 3. Environment Variables (`Backend/.env`)
```env
GCP_PROJECT_ID=...
GCP_REGION=...
GEMINI_MODEL_NAME=gemini-2.0-flash
QDRANT_HOST=localhost
QDRANT_PORT=7000
```

---

## 🌐 Deployment & Staging

The application is deployed via Docker Compose on the staging server (`192.168.1.250`).

### Access Points
- **Web App**: `http://192.168.1.250:4040`
- **API Engine**: `http://192.168.1.250:8000`

### Update Workflow
1. **Local**: `git push origin <your-feature-branch>`
2. **Server**: `ssh administrator@192.168.1.250 "cd ~/mkt-int/Market-Intelligence-Tool && git pull && docker compose restart"`

---

## 🌓 Architectural Decisions
- **Thread-Safe Concurrency**: Migrated from `asyncio` locks to standard `threading.Lock` to support stable multi-user query handling within Flask's threaded architecture.
- **Static Frontend Delivery**: Switched to `outputMode: "static"` to bypass SSR hydration conflicts in local development environments.
- **Security & Hygiene**: All secret keys and service accounts are purged from Git history and managed via environment variables.

---

*Engineered for Speed. Built for Insight. Maintained by Emmanuel Maina.*