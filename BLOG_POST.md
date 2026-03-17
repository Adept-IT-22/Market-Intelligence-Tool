# Building Adept's Internal LLM

## A 3-Level Hierarchical RAG Architecture

At **Adept Technologies**, we deal with a unique challenge: providing deterministic, verifiable market intelligence grounded in primary economic documents, sector reports, and structured data sources to aid our decision-making. Unlike general-purpose AI, our requirements are strict—every answer must be grounded in specific, often unstructured documents like sector reports, project sheets, and economic forecasts.

When we set out to build the **Adept Internal LLM**, we realized that standard Retrieval-Augmented Generation (RAG) wasn't enough. We didn't just need a chatbot; we needed a **Precision Data Scout**—a system that could navigate through Kenyan market intelligence with surgical precision.

In this post, we'll dive into the architecture of our 3-level RAG pipeline, the production-grade decisions that ensure our system remains reliable, and how we measure success in an era of AI hallucinations.

---

## System Architecture Overview

Our production stack is designed for deterministic retrieval and high-availability market research. We avoid "naive RAG" in favor of a layered orchestration approach.

- **Backend Framework**: Flask (Python, synchronous with ThreadPoolExecutor for parallel I/O)
- **Vector Database**: Qdrant (Semantic retrieval with 384-dimensional vectors)
- **Metadata Store**: SQLite (Deterministic routing index for hierarchical navigation)
- **LLM Provider**: DeepSeek Chat API (Multi-step routing & synthesis)
- **Embedding Model**: `BAAI/bge-small-en` (384-dimensional vectors)
- **Concurrency Control**: `ThreadPoolExecutor` for parallel L3 retrieval (2 workers)
- **Caching Layer**: Response-level caching for identical queries
- **Hosting**: Locally hosted (with Docker containerization support)

### The Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    User Query                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   Cache Check        │
            │   (Hit = Return)      │
            └──────────┬───────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │  Level 1: Master Router                   │
        │  Query Master Table (LLM Routing)         │
        │  → Identify top 8-10 relevant sources     │
        └──────────────┬───────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │  Level 2: Scoped Scout                    │
        │  LLM-driven routing to specific tables    │
        │  → Select 5-10 SQL tables + 3-5 Qdrant   │
        └──────────────┬───────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
   ┌──────────────┐          ┌──────────────┐
   │ SQL Detail   │          │ Semantic     │
   │ Retrieval    │          │ Search       │
   │ (PARALLEL)   │          │ (PARALLEL)   │
   └──────┬───────┘          └──────┬───────┘
        │                             │
        └──────────────┬──────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │  Safety Net Logic                        │
        │  Suppress/filter semantic results        │
        │  based on hierarchical success           │
        └──────────────┬───────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │  Level 3: Synthesis (DeepSeek LLM)       │
        │  Temperature = 0.0                       │
        │  Generate grounded, cited answer         │
        └──────────────┬───────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │  Cache + Persist to History              │
        │  Return Response to User                 │
        └──────────────────────────────────────────┘
```

This layered architecture ensures that synthesis only happens after the data has been progressively narrowed and verified through three distinct stages of intelligent filtering.

---

## The 3-Level Precision Pipeline

Instead of one giant leap from query to answer, our system takes three controlled steps, with smart shortcuts for common queries.

### Level 1: Master Routing (The Map)

The first layer queries a **Master Table**—a curated SQLite index of every available data source with metadata including title, summary, and sector classification. The LLM uses this metadata to identify the top 8-10 most relevant documents.

- **Engineering Choice**: We prioritize document `Title` and `Sectors` over generic `Summary` text. Titles contain the true identity of the source, and sector tags enable precise query matching.
- **Fast Path Detection**: For greetings and small talk ("Hello", "How are you?"), we skip the entire pipeline and return a quick response in ~100ms.

### Level 2: Scoped Scouting (The Compass)

Once we have the relevant documents from Level 1, we don't dump them into the LLM. Instead, we use a second LLM call to scan the internal structure and identify exactly which SQL tables or Qdrant chunks contain the answer. This layer produces a structured list of specific sources to retrieve.

- **Result**: Instead of processing 50MB of context, we narrow to 20KB of relevant data.

### Level 3: Detail Hydration (The Deep Dive) — PARALLEL EXECUTION

This is where parallelization delivers significant performance gains. We simultaneously:

1. **SQL Path**: Fetch raw rows from selected SQL tables into DataFrames
2. **Semantic Path**: Perform vector search in Qdrant (top 5 results as a safety net)

Using `ThreadPoolExecutor(max_workers=2)`, both operations happen concurrently, reducing total latency by ~40%.

#### Safety Net Logic

After parallel retrieval, we apply intelligent filtering:

```
if (hierarchical_context_size > 2000 chars) AND (query_length > 4 words):
    → SUPPRESS semantic results (avoid noise)
    → Trust the hierarchy
else:
    → KEEP top-3 semantic results (fallback/safety net)
```

This ensures strong hierarchical data doesn't get drowned out by semantic noise, while weak hierarchies benefit from the safety net.

> **Result**: Our LLM processes 2,000-20,000 characters of highly relevant context while maintaining extreme precision, minimizing the "needle in a haystack" problem.

---

## Query Routing: Three Distinct Paths

Our system intelligently routes queries to different execution paths based on content:

### Path A: Fast Path (Greetings)
```
"Hello" / "How are you?" / "What's your name?"
    ↓
Fast path detection
    ↓
Return greeting response (~100ms, no retrieval)
```

### Path B: General Query (Data Exploration)
```
"What data do you have?" / "Show me available sources"
    ↓
Master routing only
    ↓
Return data summary with available tables (~1-2s)
```

### Path C: Research Query (Full Pipeline)
```
"I'm a farmer in Limuru wanting to sell excess maize. 
 How do I go about it and am I in the right location?"
    ↓
Level 1 → Level 2 → Level 3 (PARALLEL) → Synthesis
    ↓
Comprehensive answer with citations (~5-15s)
```

---

## Why Hybrid Search Beats Pure Vector Search

Vector search excels at semantic similarity but can miss exact entity references or specific data points. Pure vector search might retrieve *"East Africa Economic Overview"* when a user asks for *"Kenya GDP 2024"*.

By combining semantic search (Qdrant) with keyword-based routing (SQLite + LLM), we solve:

- **Semantic Misses**: Catching related concepts (e.g., "Maize" vs "Corn").
- **Exact Match Precision**: Identifying specific document IDs, report dates, and sector classifications.
- **Entity Retrieval Accuracy**: Ensuring that specific proper nouns (locations like "Limuru", company names, products) are weighted correctly.
- **Hierarchical Navigation**: Using metadata to navigate from broad topics to specific data points.

---

## Evaluation and Performance

We evaluated the system using hundreds of real-world analyst queries to move beyond "vibes-based" engineering.

**Metrics**:

- **Retrieval Precision**: >90% (relevant sources selected in Level 1 & 2)
- **Grounded Answer Rate**: ~97% (citations to actual retrieved data)
- **Hallucination Rate**: <1% (temperature=0.0 enforcement)
- **Average Latency**: 3-8 seconds (depending on query complexity)
- **P95 Latency**: 12-15 seconds

### Latency Breakdown

To maintain operational maturity, we monitor the distribution of processing time:

- **Cache Check**: <10ms (cache hit: return immediately)
- **Level 1 Routing**: ~200-300ms
- **Level 2 Scouting**: ~400-500ms
- **Level 3 Hydration** (parallel):
  - SQL retrieval: ~300-400ms
  - Semantic search: ~200-300ms
  - Combined (parallel): ~400ms
- **Synthesis (LLM)**: ~800-1200ms
- **Total**: ~3-8 seconds (avg) / ~12-15s (P95)

> **Optimization**: Parallel execution at Level 3 saves 40-50% on retrieval time compared to sequential execution.

---

## The Foundation: Embeddings, Semantics, and Vector Space

### 1. What are Embeddings? (The Number Translation)

Computers cannot read English, but they excel at math. An **Embedding** turns text into a **Vector** (a list of numbers). In our system, `BAAI/bge-small-en` transforms words and sentences into coordinates in a 384-dimensional space.

### 2. Semantics: Meaning vs. Keywords

Because "Maize" and "Corn" sit close to each other in mathematical space, the AI understands they are related. **Distance in vector space = Semantic similarity.**

### 3. Vectors & Qdrant: The High-Speed Library

Searching thousands of 384-dimensional vectors requires specialized indexing. **Qdrant** uses HNSW (Hierarchical Navigable Small World) algorithms to instantly find text chunks whose semantic meaning matches the query.

---

## The "Deep Dive": Why Temperature 0.0?

In LLM engineering, **Temperature** is the "creativity dial." We hardcode this to **0.0** because market intelligence is a science, not poetry.

1. **Determinism and Reliability**: Analysts need identical answers for identical queries. $T=0$ ensures the model always picks the highest-probability token, not a random alternative.
2. **Eliminating Imaginative Hallucinations**: $T=0$ forces the model to stay within the "contextual fence" of our retrieved data. It cannot "imagine" facts outside the context.
3. **Precision in Structured Output**: Level 2 routing relies on stable, parseable JSON/CSV output. High temperature causes syntax drift; $T=0$ ensures structural integrity.

---

## Caching Layer: Avoiding Redundant Computation

To reduce latency and API costs, we implement response-level caching:

```python
cached_response = get_cached_response(user_query)
if cached_response:
    return cached_response  # 0ms latency
else:
    result = manager.pipeline()
    set_cached_response(user_query, result)
    return result
```

For identical or near-identical queries, this eliminates the entire pipeline, returning a cached response in milliseconds.

---

## Concurrency & Parallel Execution

To optimize latency, we run SQL and vector retrieval in parallel:

```python
with ThreadPoolExecutor(max_workers=2) as executor:
    future_details = executor.submit(self.get_detail_content, selection)
    future_semantic = executor.submit(self.search_qdrant, top_k=5)
    
    detail_context = future_details.result()      # SQL results
    semantic_results = future_semantic.result()   # Vector results
```

This concurrent I/O design reduces Level 3 latency from ~800ms (sequential) to ~400ms (parallel), a **50% improvement**.

---

## Observability and Monitoring

We continuously monitor system performance using structured logging and execution time tracking.

Key signals tracked:

- **Cache hit rate** (indicates query patterns)
- **Latency distribution** (P50, P95, P99)
- **Pipeline path selection** (fast/general/research)
- **Hierarchical vs. semantic context balance**
- **LLM synthesis quality** (citation accuracy, grounding)
- **Error rates and exception types**

This allows us to detect regressions early and maintain system reliability.

---

## Why DeepSeek? Our LLM Choice

We chose **DeepSeek Chat API** over alternatives like Gemini or GPT-4 for several reasons:

- **Superior instruction following** for multi-step routing logic (Level 2 complexity)
- **Cost-effectiveness** for high-volume analyst queries
- **Consistent performance** on structured output (JSON routing)
- **Reliable API** with predictable rate limits
- **Fast inference** (sub-second responses for synthesis)

---

## Failure Modes and Mitigations

No retrieval system is perfect. We explicitly engineered safeguards against common failure modes.

| Failure Mode | Mitigation |
|---|---|
| **Incorrect document routing** | Hybrid ranking (semantic + keyword) + LLM validation |
| **Context overflow** | Hierarchical 3-level routing ensures only relevant segments are hydrated |
| **Hallucinated synthesis** | Temperature = 0.0 + context restriction |
| **Safety net noise** | Adaptive filtering based on hierarchical success |
| **Duplicate query waste** | Response caching layer |
| **Slow semantic search** | Parallel execution with ThreadPoolExecutor |

By explicitly designing for failure containment, we ensure predictable and trustworthy system behavior.

---

## Chat History & Contextual Awareness

Each query execution passes chat history to the AgentManager, enabling:

- **Multi-turn conversations**: The LLM understands previous messages in the session
- **Context continuity**: Follow-up questions reference prior context
- **Session persistence**: Chat history is stored in SQLite for audit trails

---

## Future Improvements

We are actively working on the next generation of our infrastructure:

- **Query Compression**: Summarize long chat histories before passing to LLM
- **Adaptive Caching Strategies**: More intelligent cache invalidation and TTL management
- **Streaming Responses**: Real-time token streaming for better UX
- **Fine-tuned Embedding Models**: Domain-specific embeddings optimized for Kenyan economic data
- **Automated Data Ingestion**: Full automation from source document to indexed knowledge base
- **Multi-modal RAG**: Supporting PDFs, images, and tabular data natively
- **Fallback Chain**: Graceful degradation when primary LLM provider is unavailable

---

## Conclusion

Building a production-grade RAG system requires more than just throwing vectors and LLMs together. Our 3-level hierarchical architecture, combined with caching, parallel execution, and safety net logic, enables us to deliver:

✅ **Precision**: >90% retrieval accuracy  
✅ **Reliability**: <1% hallucination rate  
✅ **Performance**: 3-8 second average latency  
✅ **Determinism**: Identical answers for identical queries  
✅ **Scalability**: Concurrent query handling with intelligent resource management  

This is what production-grade market intelligence looks like.

