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
- **Optimized Pipeline**: A consolidated agent architecture that minimizes LLM calls and maximizes throughput.
- **Smart Routing**: Hybrid retrieval logic that combines structured SQL data with unstructured vector context.

### 🎨 Premium UI/UX
- **Modern Chat Interface**: A "Chat-First" user experience inspired by industry-leading AI tools.
- **Dark/Light Mode**: Full theme support with seamless transitions, managed via Angular Signals.
- **Glassmorphism Design**: Sleek, modern aesthetics with backdrop-blur effects and premium typography (`Inter` & `Outfit`).
- **Responsive Layout**: Sticky navigation and a collapsible sidebar for efficient workflow.
- **Skeleton Loading**: Smooth animations provide immediate feedback during data synthesis.

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
QDRANT_PORT=7000
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

## 📐 Architecture

1. **Query Ingestion**: User enters a natural language query via the Angular chat interface.
2. **Context Retrieval**:
    - **Vector Search**: Search Qdrant for semantic matches in the knowledge base.
    - **Relational Search**: Query SQLite for structured data based on identified table schemas.
3. **Synthesis**: The Backend sends the consolidated context to Groq's Llama-3 model.
4. **Response**: A markdown-formatted, data-cited response is streamed back to the frontend.

---

## 🌓 Dark/Light Mode
The application supports persistent theme switching. Use the toggle button in the top navigation bar to switch between the sleek dark theme and the crisp light theme.

---

*Generated and Maintained by Emmanuel Maina*