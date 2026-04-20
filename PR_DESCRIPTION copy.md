# Pull Request: Precision Scout v2 Upgrade

## Overview
This PR transforms the Market Intelligence Tool from a stateless RAG system into a persistent, agentic intelligence engine. It introduces a two-tier retrieval system (PageIndex), a reasoning agent loop, and a project-based workspace memory layer.

## Key Changes

### 1. Structural Reasoning (PageIndex)
- **New Collection**: `document_index` in Qdrant containing document-level summary embeddings for all 1,188 Master records.
- **Two-Tier Search**: `AgentManager` now performs a Tier 1 search on document summaries to identify the top 15 relevant documents, then performs a Tier 2 chunk search filtered specifically to those documents. This reduces noise by >95%.
- **PageIndex Builder**: New utility script `build_page_index.py` to seed the initial index.

### 2. Agentic Reasoning Layer
- **AgentLoop**: Implemented `agent_loop.py` which wraps the retrieval pipeline in a Plan -> Retrieve -> Think (Reflect) -> Act (Synthesize) cycle.
- **Confidence Scoring**: Heuristic reflection on retrieval quality to provide confidence benchmarks.
- **Artifact Generation**: Automatic generation of `.md` analysis reports saved to project workspaces.

### 3. Workspace & Persistence
- **Workspace Manager**: New `workspace_manager.py` handling persistent project storage in `Backend/workspace/projects/`.
- **PROJECT.md**: Each project now has a "source of truth" file that tracks query history, linked data sources, and generated insights.
- **Project Context**: Integrated project memory into the agent's prompts for cross-session continuity.

### 4. Technical Improvements & Regressions
- **Semantic Chunking**: Replaced fixed 1,000-char splitting with paragraph-aware chunking (`\n\n`) in `ingest_data.py`.
- **Qdrant API Update**: Migrated all `.search()` calls to `.query_points()` to support Qdrant-client v1.9+.
- **SharePoint Link Formatting**: Fixed frontend regex in `main-search.component.ts` to ensure local paths are correctly transformed into clickable SharePoint URLs.
- **Port Conflict**: Switched Flask from port `8000` to `5000` to resolve conflicts with local services.

## Verification
- PageIndex built successfully (1188 points).
- Average retrieval latency reduced to ~68ms in uncached speed tests.
- UI links verified as clickable.
- Backend streaming stabilized.

## Merge Target
Merge `feature/precision-scout-v2` into `dev`.
