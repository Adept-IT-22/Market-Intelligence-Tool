# 🇰🇪 Market Intelligence Tool

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Angular](https://img.shields.io/badge/angular-19-red.svg)
![Groq](https://img.shields.io/badge/inference-Groq-orange.svg)
![Qdrant](https://img.shields.io/badge/vector--db-Qdrant-green.svg)

A high-performance, AI-driven analytics platform designed to provide deep insights into the Kenyan market. Leveraging cutting-edge LLM inference and Retrieval Augmented Generation (RAG), this tool delivers precise, data-backed answers in seconds.

---

## ✨ Key Features

### 🚀 Performance & Intelligence
- **Ultra-Fast Inference**: Integrated with **Groq** using `llama-3.1-8b-instant` for sub-second response times.
- **Retrieval Augmented Generation (RAG)**: Uses **Qdrant** vector database to ground AI responses in actual market intelligence documents.
- **Hybrid Retrieval Logic**: A sophisticated 3-level filtering system:
  1. **Master Routing**: High-level semantic + keyword search across document titles.
  2. **Vector Hydration**: Automatically resolves SQL pointers (UUIDs) to full text payloads in Qdrant.
  3. **Context Synthesis**: Intelligent prompt engineering that prioritizes precise data segments.
- **Optimized Pipeline**: A consolidated agent architecture that minimizes LLM calls and maximizes throughput.
- **Smart Routing**: Combines structured SQL data with unstructured vector context.
- **Auto-Ingestion**: Supports remote file ingestion from SharePoint via **Power Automate** and **ngrok**. (See [POWER_AUTOMATE_GUIDE.md](./POWER_AUTOMATE_GUIDE.md))

### 🎨 Premium UI/UX
- **Threaded Chat Tree**: Visual conversation history connecting user queries and AI responses with threaded connectors.
- **Interactive Actions**: Edit previous queries, copy AI responses, and view execution time metrics directly in the chat.
- **Typing Animations**: GSAP-powered typewriter effects for natural, streaming-like text delivery.
- **Dark/Light Mode**: Full theme support with high-contrast visibility for sidebar, managed via Angular Signals.
- **Glassmorphism Design**: Sleek, modern aesthetics with backdrop-blur effects and premium typography (`Inter` & `Outfit`).
- **Responsive Layout**: Sticky navigation and a collapsible sidebar for efficient workflow.
- **Enhanced Loading**: Dynamic step indicators ("Scanning...", "Synthesizing...") providing granular feedback.

---

## 🛠️ Tech Stack

- **Frontend**: Angular 19, Angular Material, Tailwind-inspired Vanilla CSS.
- **Backend**: Flask (Python), Groq SDK.
- **Vector Database**: Qdrant (Running locally on port 7000).
- **Relational Database**: SQLite (for structured master-detail data).
- **Embeddings**: `sentence-transformers` (BAAI/bge-small-en).

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js & npm
- Qdrant Server (Running locally)

### 2. Backend Setup
```bash
cd Backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```
Create a `.env` file in the `Backend` directory:
```env
GROQ_API_KEY=your_groq_api_key
QDRANT_HOST=localhost

```
Run the backend:
```bash
python main.py
```

### 3. Frontend Setup
```bash
cd Front-end/Market-Intelligence
npm install
npm start
```
The application will be available at `http://localhost:4200`.

### 4. Vector Database Setup
Ensure Qdrant is running on port 7000. To populate the vector store with your local data:
```bash
cd Backend
python setup_qdrant.py
```

---

## 🌐 Deployment (Staging Server)

The application is deployed via Docker Compose on the staging server (`192.168.1.250`).

### Access
- **Frontend**: `http://192.168.1.250:8080`
- **Backend API**: `http://192.168.1.250:8000`

### Updating Code
To push local changes to the staging server:
1. **Push to GitHub**: `git push origin dev`
2. **Pull on Server**: `ssh administrator@192.168.1.250 "cd ~/mkt-int/Market-Intelligence-Tool && git pull origin dev"`
3. **Restart Service**: `ssh administrator@192.168.1.250 "cd ~/mkt-int/Market-Intelligence-Tool && docker compose restart backend"`

### Data Sync (Local -> Server)
If you ingest new data locally and want to sync it:
1. **Migrate Vectors**: Run `Backend/migrate_vectors.py` (requires SSH tunnel to port 16333).
2. **Upload Database**: `scp Backend/DB/market-intelligence.db administrator@192.168.1.250:~/mkt-int/Market-Intelligence-Tool/Backend/DB/`

---

## 🌓 Architectural Decisions

- **SSR to Static Mode**: The frontend was recently switched from `outputMode: "server"` to `outputMode: "static"` to resolve local platform boot errors (`NG0401`), improving stability in local development environments while preserving full RAG functionality.
- **Traceable Citations**: AI responses now use mandatory `[Filename](URI)` markdown citations. For **local development only**, the frontend's markdown sanitizer is configured to `SecurityContext.NONE` to allow functional `file:///` links to local documents. **Warning:** `SecurityContext.NONE` disables Angular's built-in XSS protection for this content and **must not** be used in production or with untrusted input.
---

## 🌓 Dark/Light Mode
The application supports persistent theme switching. Use the toggle button in the top navigation bar to switch between the sleek dark theme and the crisp light theme.

---

*Generated and Maintained by Emmanuel Maina*