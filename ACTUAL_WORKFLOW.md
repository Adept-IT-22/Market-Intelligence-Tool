# Market Intelligence Tool - Actual Workflow Documentation

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         API Backend (Flask)                              │
│                            main.py                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                        ┌─────────┴─────────┐
                        ▼                   ▼
                  ┌──────────────┐    ┌────────────────┐
                  │ Cache Check  │    │ Auth & Session │
                  │ (Redis-like) │    │  Management    │
                  └──────────────┘    └────────────────┘
                        │                   │
                        └─────────┬─────────┘
                                  ▼
                        ┌──────────────────────┐
                        │  AgentManager        │
                        │  Pipeline Start      │
                        └──────────────────────┘
```

---

## Detailed Query Processing Pipeline

### Phase 1: Pre-Pipeline Validation (main.py)

```
User Query Request
        │
        ▼
┌─────────────────────────┐
│  Validate JSON Body     │
│  Extract query field    │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  Check Cache Layer      │
│  (get_cached_response)  │
└─────────────────────────┘
        │
    ┌───┴───┐
    │       │
   YES     NO (CACHE HIT)
    │       │
    │       ▼
    │   Return Cached Response
    │   + Persist to History
    │
    ▼
┌────────────────────────────┐
│  Extract User Context:     │
│  - User ID                 │
│  - Session ID              │
│  - Chat History            │
└────────────────────────────┘
    │
    ▼
┌────────────────────────────┐
│ Initialize AgentManager    │
│ with:                      │
│  - query                   │
│  - chat_history            │
│  - embeddings              │
└────────────────────────────┘
```

---

### Phase 2: AgentManager.pipeline() - Three-Level RAG

```
┌─────────────────────────────────────────────────────────────────────┐
│                    START PIPELINE                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  FAST PATH CHECK    │
                    │ (Greetings/Small   │
                    │  Talk Detection)    │
                    └─────────────────────┘
                              │
                         ┌────┴────┐
                         │         │
                      MATCH      NO MATCH
                         │         │
                         ▼         ▼
                    [Return    Continue to
                    Response]  Level 1

        ┌──────────────────────────────────────────────────────┐
        │              LEVEL 1: MASTER ROUTER                   │
        │              get_master_routing()                     │
        └──────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴──────────────┐
                │                            │
                ▼                            ▼
        ┌──────────────────┐      ┌──────────────────┐
        │ Query Master     │      │ Extract Routing  │
        │ Table via LLM    │      │ Tables from DB   │
        │ (List relevant   │      │ (SQL + Qdrant)   │
        │  tables)         │      └──────────────────┘
        └──────────────────┘
                │
                └────────────┬────────────┘
                             │
                             ▼
                    ┌──────────────────────┐
                    │ GENERAL QUERY CHECK  │
                    │                      │
                    │ Keywords:            │
                    │ - "what data"        │
                    │ - "available data"   │
                    │ - "show me sources"  │
                    └──────────────────────┘
                             │
                        ┌────┴────┐
                     MATCH      NO MATCH
                        │          │
                        ▼          ▼
                   [Return    Continue to
                   Data       Level 2
                   Summary]

        ┌──────────────────────────────────────────────────────┐
        │         LEVEL 2: SCOPED SCOUT / ROUTING ENGINE       │
        │           get_routing_response()                      │
        └──────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴──────────────┐
                │                            │
                ▼                            ▼
        ┌──────────────────┐      ┌──────────────────┐
        │ SQL Tables       │      │ Qdrant Tables    │
        │ Selection via    │      │ Selection via    │
        │ LLM Routing      │      │ LLM Routing      │
        │ (5-10 most       │      │ (3-5 most        │
        │  relevant)       │      │  relevant)       │
        └──────────────────┘      └──────────────────┘
                │                           │
                └───────────┬───────────────┘
                            │
                            ▼
                   ┌──────────────────────┐
                   │ SELECTION OUTPUT     │
                   │ {                    │
                   │   "SQL": [...],      │
                   │   "Qdrant": [...]    │
                   │ }                    │
                   └──────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│   LEVEL 3A: DETAIL CONTENT   │   │ LEVEL 3B: SEMANTIC SEARCH    │
│  get_detail_content()        │   │ search_qdrant(top_k=5)       │
│  (Hierarchical Path)         │   │ (Safety Net Path)            │
│                              │   │                              │
│ - Read SQL rows from chosen  │   │ - Vector encode query        │
│   tables into DataFrames     │   │ - Query Qdrant collection    │
│ - Read detailed content      │   │ - Return top-5 similar       │
│ - Format for LLM             │   │   semantic chunks            │
│                              │   │                              │
└──────────────────────────────┘   └──────────────────────────────┘
        │                                       │
        │         ┌─────────────────┐          │
        └─────────┤ PARALLEL EXEC   ├──────────┘
                  │ (ThreadPool)    │
                  └─────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │  SAFETY NET LOGIC                        │
        │  ────────────────────────────────────────│
        │  if hierarchical_success AND             │
        │     query_length > 4 words:              │
        │     ↳ SUPPRESS semantic results          │
        │       (keep focus on hierarchy)          │
        │  else:                                   │
        │     ↳ KEEP top-3 semantic results        │
        │       (fallback/supplement)              │
        └──────────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │  CONTEXT PACKAGING                       │
        │  {                                       │
        │    "Hierarchical Data": detail_context   │
        │    "Semantic Data": semantic_context     │
        │    "Routing Tables": routing_tables      │
        │  }                                       │
        └──────────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────────┐
        │   SYNTHESIS: LLM FINAL RESPONSE          │
        │   get_final_response()                   │
        │                                          │
        │ - Combine hierarchical + semantic data   │
        │ - Generate insights with citations      │
        │ - Include counter-arguments             │
        │ - Suggest research directions           │
        │ - Format for user readability           │
        └──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────┐
│         RETURN RESPONSE & PERSIST                │
│                                                  │
│  - Cache the response                           │
│  - Save to chat history                         │
│  - Record execution time                        │
│  - Return to Flask endpoint                     │
└──────────────────────────────────────────────────┘
```

---

## Data Flow: Inputs to Outputs

```
┌─────────────────────────────┐
│   User Query & Context      │
│                             │
│  query: str                 │
│  session_id: int (optional) │
│  user_id: int (optional)    │
│  chat_history: list         │
│  stream: bool               │
└─────────────────────────────┘
            │
            ▼
    ┌──────────────────┐
    │  AgentManager    │
    │  __init__()      │
    └──────────────────┘
            │
            ├─── embeddings: SentenceTransformer
            ├─── query_vector: np.array (1D)
            ├─── qdrant_client: QdrantClient
            ├─── llm_client: OpenAI (DeepSeek)
            └─── database_path: str
            
            │
            ▼
    ┌──────────────────┐
    │  pipeline()      │
    │  or             │
    │  pipeline_stream│
    └──────────────────┘
            │
            ├─── Master schema: dict
            ├─── Routing tables: dict
            ├─── Detail content: str (2000-20000 chars)
            ├─── Semantic results: list[PointStruct]
            └─── Final response: str
            
            │
            ▼
    ┌──────────────────┐
    │  Flask Endpoint  │
    │  /query (POST)   │
    └──────────────────┘
            │
    ┌───────┴──────────┐
    │                  │
    ▼                  ▼
[JSON Response]  [Server-Sent Events]
+ execution_time + streaming chunks
+ cached flag    + final execution_time
```

---

## Data Storage & Retrieval

### SQLite Database Structure
```
Master Table (Metadata)
├── table_name: str
├── Title: str
├── Summary: str
├── Sectors: str
├── Datatype: str (SQL or Qdrant)
└── table_name: str (reference)

Detail Tables (Data)
├── {various columns based on table}
├── {product-specific data}
└── {market data}

Chat History (models.py)
├── user_id: int
├── session_id: int
├── messages: list[{role, content, timestamp}]
└── execution_time: float
```

### Qdrant Vector Database
```
Collection: adept_database

Point Structure:
├── id: int
├── vector: list[384] (BAAI/bge-small-en embedding)
├── payload:
│   ├── text: str (document chunk)
│   ├── source: str (document URI)
│   ├── metadata: dict
│   └── timestamp: str
└── score: float (similarity to query)
```

---

## Streaming vs. Non-Streaming

### Non-Streaming (Default)
```
User Request
    │
    ▼
Pipeline runs to completion
    │
    ▼
Full response returned as JSON
    │
    ▼
Single HTTP response
```

### Streaming (with stream=true)
```
User Request
    │
    ▼
Pipeline yields chunks as they're generated
    │
    ▼
Server-Sent Events (SSE) stream
    │
    ├─── data: {chunk: "text..."}
    ├─── data: {chunk: "more text..."}
    ├─── data: {chunk: "final chunk..."}
    │
    ▼
    data: {done: true, execution_time: 12.5}
```

---

## Error Handling & Fallbacks

```
Pipeline Execution
        │
        ▼
    ┌───────────┐
    │ Try Block │
    └───────────┘
        │
    ┌───┴───┐
    │       │
   OK    ERROR
    │       │
    │       ▼
    │   Log Exception
    │   │
    │   ▼
    │   Return 500 + Error Message
    │
    ▼
Success → Cache + History + Response
```

---

## Performance Optimizations

### 1. **Parallel Execution (Level 3)**
```python
with ThreadPoolExecutor(max_workers=2) as executor:
    future_details = executor.submit(self.get_detail_content, selection)
    future_semantic = executor.submit(self.search_qdrant, top_k=5)
    
    detail_context = future_details.result()
    semantic_results = future_semantic.result()
```
- SQL reads and vector search happen **simultaneously**
- Reduces latency by ~40-50%

### 2. **Adaptive Filtering**
```python
hierarchical_success = len(detail_context) > 2000

if is_research_query and hierarchical_success:
    semantic_results = []  # Suppress noise
else:
    semantic_results = semantic_results[:3]  # Keep relevant
```
- Prevents "noise" when hierarchy is strong
- Keeps safety net when hierarchy is weak

### 3. **Response Caching**
```python
cached = get_cached_response(user_query)
if cached:
    return cached  # Instant response, 0ms latency
```
- Redis-like caching for identical queries
- Significantly reduces LLM API calls

### 4. **Fast Path Detection**
```python
if self._check_fast_path():  # Greetings, small talk
    return quick_response()  # Skip all retrieval
```
- Skips the entire 3-level pipeline for simple queries

---

## Query Types & Their Paths

### Path A: Fast Path (Greetings)
```
"Hello" / "How are you?" / "What's your name?"
            │
            ▼
        _check_fast_path()
            │
            ▼
        get_final_response() [simplified]
            │
            ▼
        ~100ms response
```

### Path B: General Query
```
"What data do you have?" / "Show me sources"
            │
            ▼
        get_master_routing()
            │
            ▼
        get_final_response() [with data summary]
            │
            ▼
        ~1-2s response
```

### Path C: Research Query
```
"I'm a farmer in Limuru wanting to sell excess maize. 
 How do I go about it?"
            │
            ▼
        get_master_routing()
            │
            ▼
        get_routing_response()
            │
            ▼
        PARALLEL:
        ├── get_detail_content()
        └── search_qdrant()
            │
            ▼
        get_final_response() [comprehensive]
            │
            ▼
        ~5-15s response
```

---

## Configuration & Environment Variables

```
.env file:
├── DEEPSEEK_API_KEY
├── DEEPSEEK_BASE_URL = "https://api.deepseek.com"
├── QDRANT_HOST = "localhost"
├── QDRANT_PORT = "8000"
├── QDRANT_URL = "http://localhost:8000"
├── DATABASE_PATH = "DB/market-intelligence.db"
├── LLM_MODEL_NAME = "deepseek-chat"
├── EMBEDDING_MODEL = "BAAI/bge-small-en"
└── COLLECTION_NAME = "adept_database"
```

---

## Key Differences from Initial Diagrams

| Aspect | Initial Diagram | Actual Workflow |
|--------|-----------------|-----------------|
| **Caching** | Not shown | Cache check before pipeline |
| **Parallel Execution** | Sequential | ThreadPoolExecutor(L3A + L3B) |
| **Safety Net** | Simple | Adaptive suppression logic |
| **Query Types** | Single path | 3 distinct paths (fast/general/research) |
| **Streaming** | Not shown | SSE support in parallel |
| **Chat History** | Not shown | Passed to AgentManager initialization |
| **Error Handling** | Not shown | Try-catch with detailed logging |
| **API Integration** | Generic "LLM" | Specific DeepSeek API calls with retry logic |

---

## Summary: Complete Request Lifecycle

```
1. [MAIN.PY - REST API Handler]
   └─ POST /query
      ├─ Validate JSON
      ├─ Check cache ← RETURN if HIT
      ├─ Extract context (user, session, history)
      └─ Create AgentManager instance

2. [AGENT_MANAGER - Intelligent Retrieval]
   └─ pipeline() or pipeline_stream()
      ├─ Check fast path ← RETURN if match
      ├─ Level 1: Master router (what to search)
      ├─ Check general query ← RETURN if match
      ├─ Level 2: Routing engine (which sources)
      ├─ Level 3 (PARALLEL):
      │  ├─ Hierarchical: get_detail_content()
      │  └─ Semantic: search_qdrant()
      ├─ Apply safety net logic
      ├─ Synthesis: get_final_response()
      └─ RETURN rich context + insights

3. [MAIN.PY - Response Handler]
   ├─ Cache response
   ├─ Persist to chat history
   ├─ Measure execution time
   └─ Return JSON or stream

4. [FRONTEND - User Display]
   └─ Render formatted response
      ├─ Display insights
      ├─ Show sources with citations
      ├─ Include counter-arguments
      └─ Suggest next research directions
```

