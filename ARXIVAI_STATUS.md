# ArxivAI v2.0 — Project Status Tracker

Paste this file into any AI assistant at session start for full context.
Format: ✅ Done | 🔄 In Progress | ⬜ Not Started | ❌ Blocked | ⚠️ Changed from original plan

**Last updated:** 2026-07-11
**Current focus:** Search quality — hybrid search implementation
**Sessions completed:** ~10+

---

## ⚠️ CRITICAL TECH STACK CHANGES (Original Plan vs. Actual)

The original Claude project instructions are **outdated**. These are the actual decisions made during development:

| Layer | Original Plan | **Actual Implementation** | Why Changed |
|---|---|---|---|
| Vector Database | Chroma (self-hosted) | **Supabase pgvector** | Chroma had persistent metadata filter crashes; Supabase gives managed DB + vector in one |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` | **AWS Bedrock `amazon.titan-embed-text-v2:0`** | Free, cloud-managed, no GPU needed, 512-dim Matryoshka support |
| Vector Dimensions | 384 (MiniLM) | **512 (Titan V2 Matryoshka)** | Matches our pgvector column definition |
| Models DB | PostgreSQL (separate) | **Supabase PostgreSQL** (same instance) | Single managed DB for both metadata and vectors |
| File Storage | MinIO / AWS S3 | **Not yet implemented** | PDFs downloaded directly from arXiv URLs; user upload storage deferred |
| Local LLMs | Ollama primary | **Groq API primary** (Ollama removed) | Student machine can't run 7B+ models; Groq free tier works well |
| All models merged | Separate files per domain | **Single `src/models.py`** (all 13 tables) | Easier to manage relationships and migrations in one place |
| All agents split | Separate files per agent | **Single `src/agents/nodes.py`** (all node functions) | Reduced import complexity; graph compiled in `graph.py` |
| Chroma metadata filters | Chroma `where` filters | **SQL WHERE clauses in pgvector** | Native SQL access control is cleaner and more flexible |

---

## 📊 OVERALL PROGRESS

```
Foundation & DB Setup        ████████████████████  100% ✅
Embeddings & Ingestion       ████████████████████  100% ✅ (AWS Bedrock)
Vector Search (Basic)        ████████████████████  100% ✅ (pgvector)
LangGraph 7-Agent Pipeline   ████████████████░░░░   80% 🔄
Hybrid Search (planned)      ░░░░░░░░░░░░░░░░░░░░    0% ⬜
Auth & User System           ████████████████████  100% ✅
Papers CRUD                  ████████░░░░░░░░░░░░   40% 🔄
Collaboration System         ████░░░░░░░░░░░░░░░░   20% 🔄
Monitoring (Prometheus)      ████████████████░░░░   80% ✅
Tests                        ░░░░░░░░░░░░░░░░░░░░    0% ⬜
Deployment (Docker)          ████████████████████  100% ✅ (local)
AWS EC2 Production           ░░░░░░░░░░░░░░░░░░░░    0% ⬜
```

---

## 🗂️ FILE-BY-FILE STATUS

### Root Level

| Status | File | Notes |
|:---|:---|:---|
| ✅ | `.env` | All secrets loaded here — DB, Groq, AWS Bedrock, JWT |
| ✅ | `requirements.txt` | Includes: fastapi, sqlalchemy, langchain, boto3, PyPDF2, langchain-google-genai (fallback), groq |
| ✅ | `ARXIVAI_STATUS.md` | This file |
| ⬜ | `.env.example` | Not yet created |
| ⬜ | `README.md` | Not yet created |

---

### `docker/`

| Status | File | Notes |
|:---|:---|:---|
| ✅ | `docker/Dockerfile` | Multi-stage build. Copies src, installs requirements |
| ✅ | `docker/docker-compose.yaml` | Services: `arxivai-api`, `arxivai-nginx`, `prometheus`, `grafana` |
| ✅ | `docker/prometheus.yml` | Scrapes `/metrics` on API container. Trailing slash fixed |
| ✅ | `docker/nginx.conf` | Reverse proxy to FastAPI |

**Running containers:** `arxivai-api`, `arxivai-nginx`, `arxivai-prometheus`, `arxivai-grafana`
**API port:** 8000 (internal), exposed via Nginx

---

### `src/config.py` ✅

All env vars loaded via `pydantic_settings.BaseSettings`.

| Variable | Description |
|:---|:---|
| `DATABASE_URL` | Supabase PostgreSQL async connection string |
| `JWT_SECRET_KEY` | JWT signing key |
| `JWT_ALGORITHM` | HS256 |
| `JWT_EXPIRE_HOURS` | Token expiry |
| `GROQ_API_KEY` | Primary LLM provider |
| `OPENROUTER_API_KEY` | Fallback LLM |
| `GEMINI_API_KEY` | Fallback LLM |
| `ANTHROPIC_API_KEY` | Premium fallback |
| `AWS_ACCESS_KEY_ID` | Dummy value (bearer token auth bypasses this) |
| `AWS_SECRET_ACCESS_KEY` | Dummy value |
| `AWS_DEFAULT_REGION` | `us-east-1` |
| `AWS_API_KEY` | AWS Bedrock Bearer Token (`ABSK...` prefix) — set as `AWS_BEARER_TOKEN_BEDROCK` in env |

---

### `src/database.py` ✅

| Function | Status | Description |
|:---|:---|:---|
| `get_engine()` | ✅ | Async SQLAlchemy engine from `DATABASE_URL` |
| `get_async_session_maker()` | ✅ | Returns session factory (used in ingestion and searcher) |
| `get_session()` | ✅ | FastAPI `Depends()` — yields async session for routes |
| `create_all_tables()` | ✅ | Called at startup in `main.py` |

---

### `src/models.py` ✅ (Single consolidated file — all 13 tables)

> ⚠️ **Changed from original plan:** All DB models are in ONE file, not split across `auth/models.py`, `papers/models.py`, etc.

| Status | Class | Table | Key Notes |
|:---|:---|:---|:---|
| ✅ | `User` | `users` | UUID PK, email unique, bcrypt password, domains array |
| ✅ | `Paper` | `papers` | String PK (arXiv ID), `pdf_url` ✅ stored, `file_path` (S3 future), `chroma_ids` repurposed as chunk UUID list |
| ✅ | `Collaboration` | `collaborations` | direct_invite / project types |
| ✅ | `CollaborationMember` | `collaboration_members` | Many-to-many users ↔ collaborations |
| ✅ | `CollaborationPaper` | `collaboration_papers` | Papers linked to collaborations |
| ✅ | `CollaborationApplication` | `collaboration_applications` | Applications for project-type collabs |
| ✅ | `Conversation` | `conversations` | Chat history per user |
| ✅ | `Message` | `messages` | Individual messages, RAGAS scores stored per message |
| ✅ | `ConversationContext` | `conversation_context` | Running context/memory per conversation |
| ✅ | `SessionState` | `session_state` | Full LangGraph agent state snapshot per query (for debugging) |
| ✅ | `ConversationSettings` | `conversation_settings` | Per-conversation user preferences |
| ✅ | `UserMemory` | `user_memory` | Persistent preferences + patterns across sessions |
| ✅ | `PGVector` | *(custom SQLAlchemy type)* | Custom `UserDefinedType` for `vector(512)` with `bind_processor` (list→string) and `result_processor` (string→list) |
| ✅ | `PaperChunk` | `paper_chunks` | pgvector table. Stores `embedding vector(512)`, `content`, `chunk_index`, `domain`, `visibility`, `user_id`, `collaboration_id` |

---

### `src/main.py` ✅

Registers routers, calls `create_all_tables()` on startup, Prometheus middleware, CORS.

| Router | Prefix | Status |
|:---|:---|:---|
| `auth/router.py` | `/auth` | ✅ |
| `papers/router.py` | `/papers` | ✅ (partial) |
| `query/router.py` | `/api/query` | ✅ |
| `collaboration/router.py` | `/collaboration` | ✅ (partial) |
| Prometheus | `/metrics` | ✅ |

---

### `src/auth/` ✅ (fully working)

> ⚠️ No `auth/models.py` — User model is in `src/models.py`

| File | Status | Notes |
|:---|:---|:---|
| `auth/schemas.py` | ✅ | `UserRegister`, `UserLogin`, `UserOut`, `TokenOut` |
| `auth/service.py` | ✅ | `hash_password`, `verify_password`, `create_access_token`, `decode_token`, `get_current_user`, `register_user`, `login_user` |
| `auth/router.py` | ✅ | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |

---

### `src/ingestion/` ✅

> ⚠️ **Restructured from original plan.** `pdf_extractor.py`, `chunker.py`, `embedder.py` were **merged into `pipeline.py`**. No separate files for those.

| File | Status | Notes |
|:---|:---|:---|
| `ingestion/arxiv_fetcher.py` | ✅ | `fetch_papers_for_domain()`, `fetch_fresh_papers()`. Returns metadata with `pdf_url`. Supports domain→arXiv category mapping (ML, NLP, CV, Systems, etc.) |
| `ingestion/pipeline.py` | ✅ | Full pipeline: download PDF → extract text → sanitize (null bytes stripped) → **chunk (1500 chars, 150 overlap)** → embed via AWS Bedrock → store in Supabase pgvector + papers table. `pdf_url` now stored in `Paper` record. |

**Key decisions in pipeline:**
- `chunk_size=1500`, `chunk_overlap=150` — chosen for academic paper paragraph completeness (vs. original 500/50)
- Null byte (`\x00`) sanitization added to fix PostgreSQL `CharacterNotInRepertoireError`
- Skip logic: if `paper_id` already has chunks in DB, it is skipped (no re-ingestion)
- `pdf_url` is now populated in `Paper` record on creation

---

### `src/vectordb/` ✅

> ⚠️ **Changed from original plan.** No Chroma at all. All vector storage is Supabase pgvector via raw SQL.

| File | Status | Notes |
|:---|:---|:---|
| `vectordb/chroma_client.py` | ✅ ⚠️ | **Misnamed — actually creates AWS Bedrock embedding client (not Chroma)**. Contains `MatryoshkaBedrockEmbeddings` wrapper that calls Titan V2 and slices output to 512 dims. `get_embedding_model()` returns this. Should be renamed to `embeddings_client.py` |
| `vectordb/searcher.py` | ✅ 🔄 | `semantic_search()` is async. Runs cosine distance query against `paper_chunks` in Supabase. `calculate_avg_relevance()` is sync. **Domain is NOT a hard SQL filter** (see decisions log). Upgrade to hybrid search planned. |

**⚠️ Known limitation — planned fix: Hybrid Search**
- Currently: pure semantic search, no domain filter at all
- Planned: Two-lane hybrid search
  - **Lane 1** (domain-filtered) → high precision results
  - **Lane 2** (no filter, global) → high recall fallback
  - **Merge**: deduplicate by `paper_id`, boost Lane 1 hits by +0.10 score, return top-k
  - Both lanes run via `asyncio.gather()` — no added latency

---

### `src/agents/` 🔄 (~80% working)

> ⚠️ **Changed from original plan.** All 7 agent node functions are in `nodes.py` (not separate files per agent).

| File | Status | Notes |
|:---|:---|:---|
| `agents/state.py` | ✅ | `RAGState` TypedDict with all fields |
| `agents/graph.py` | ✅ | LangGraph `StateGraph` compiled. Sequential: classify_domain → analyze_query → decide_search_strategy → retrieve_papers → reason_over_papers → synthesize_answer → evaluate_answer → format_output |
| `agents/nodes.py` | ✅ 🔄 | All 7 agent node functions in one file |

**Node function status:**

| Function | Status | LLM Used | Notes |
|:---|:---|:---|:---|
| `classify_domain()` | ✅ | Groq llama-3.1-8b-instant | Works. Known issue: sometimes misclassifies Systems papers as NLP/ML |
| `analyze_query()` | ✅ | Groq llama-3.1-8b-instant | Detects single_hop/multi_hop, personal, recent |
| `decide_search_strategy()` | ✅ | Groq llama-3.1-8b-instant | Sets search_spaces and fetch_arxiv_fresh |
| `retrieve_papers()` | ✅ | Groq llama-3.1-8b-instant (reformulation) | **`async def` + `await semantic_search()`** — fixed coroutine bug. Upgrade to hybrid_search planned |
| `reason_over_papers()` | ✅ | Groq llama-3.3-70b-versatile | Extracts findings, contradictions, agreements, knowledge gaps |
| `synthesize_answer()` | ✅ | Groq llama-3.3-70b-versatile | Generates answer with inline citations |
| `evaluate_answer()` | ✅ | Groq llama-3.1-8b-instant | RAGAS-style evaluation. Returns quality_score, hallucination_detected |
| `format_output()` | ✅ | — | Formats final response, deduplicates sources |

---

### `src/llm/` ✅

| File | Status | Notes |
|:---|:---|:---|
| `llm/provider.py` | ✅ | `get_llm(agent_name, mode)` — returns Groq/OpenRouter/Gemini. Fallback chain implemented. Per-agent model mapping. |
| `llm/prompts.py` | ✅ | All prompt templates: `DOMAIN_CLASSIFY_PROMPT`, `QUERY_ANALYZE_PROMPT`, `SEARCH_STRATEGY_PROMPT`, `QUERY_REFORMULATE_PROMPT`, `EXTRACT_FINDINGS_PROMPT`, `SYNTHESIS_PROMPT`, `EVALUATE_PROMPT`, etc. |

---

### `src/query/` ✅

| File | Status | Notes |
|:---|:---|:---|
| `query/router.py` | ✅ | `POST /api/query/` — accepts query, runs LangGraph pipeline, returns response |
| `query/service.py` | ✅ | `run_query()` — builds initial `RAGState`, calls `graph.ainvoke()`, returns final state |

---

### `src/papers/` 🔄 (partial)

> ⚠️ No `papers/models.py` — Paper model is in `src/models.py`

| File | Status | Notes |
|:---|:---|:---|
| `papers/schemas.py` | ✅ | `PaperUploadRequest`, `PaperOut`, `PaperVisibilityUpdate` |
| `papers/service.py` | 🔄 | Basic CRUD exists. User upload → S3 flow not implemented yet |
| `papers/router.py` | 🔄 | `/papers/upload`, `/papers/my-papers` endpoints exist but upload flow incomplete |

---

### `src/collaboration/` 🔄 (partial)

> ⚠️ No `collaboration/models.py` — all 4 collaboration models are in `src/models.py`

| File | Status | Notes |
|:---|:---|:---|
| `collaboration/schemas.py` | ✅ | Basic schemas present |
| `collaboration/service.py` | 🔄 | `create_direct_invite`, `get_user_collaborations` implemented. Apply/approve flow partial |
| `collaboration/router.py` | 🔄 | Basic endpoints present |

---

### `scripts/`

| Status | File | Notes |
|:---|:---|:---|
| ✅ | `scripts/run_ingestion.py` | CLI tool: `python run_ingestion.py --domain Systems --num 5`. Calls pipeline for multiple domains. Prints ingestion summary. |
| ✅ | `scripts/ingestion.log` | Log output from ingestion runs |
| ⬜ | `scripts/seed_domains.py` | Not yet created |

---

## 🧪 TESTS

| Status | File | Notes |
|:---|:---|:---|
| ⬜ | `tests/test_auth.py` | Not started |
| ⬜ | `tests/test_ingestion.py` | Not started |
| ⬜ | `tests/test_search.py` | Manual test done via API, no automated test yet |
| ⬜ | `tests/test_agents.py` | Not started |
| ⬜ | `tests/test_papers.py` | Not started |

---

## 🔄 PLANNED NEXT WORK (Priority Order)

### 1. Hybrid Search — Two-Lane Strategy (Next Immediate Task)

Replace the current single `semantic_search()` call with a two-lane parallel search:

```
Lane 1: domain-filtered SQL search   → high precision (may be 0 if domain mismatch)
Lane 2: global semantic search        → high recall (always returns results)

Merge strategy:
  - Deduplicate by paper_id
  - Lane 1 results get +0.10 relevance score boost
  - Sort by boosted score DESC
  - Return top-k after re-ranking
```

Both lanes run via `asyncio.gather()` — no added latency since they run in parallel.

**Files to edit:**
- `src/vectordb/searcher.py` — add `hybrid_search()` function
- `src/agents/nodes.py` — call `hybrid_search()` instead of `semantic_search()` in `retrieve_papers()`

### 2. Rename `chroma_client.py`
The file is now purely an AWS Bedrock embedding client. Should be renamed to `embeddings_client.py`.

### 3. User Paper Upload Flow
- Upload PDF → save to local volume (S3 later) → trigger ingestion pipeline as background task
- Needs `papers/service.py` completion

### 4. Domain Classifier Accuracy
- Systems papers classified as NLP/ML/CV — prompts need domain-specific examples
- Low priority since hybrid search will make domain misclassification less harmful

---

## 📝 SESSION LOG

| Date | Session # | What was done | Files changed |
|:---|:---|:---|:---|
| 2026-07-07 | 1 | Initial setup, Supabase connection, arXiv fetcher, Chroma crash debugging | `pipeline.py`, `arxiv_fetcher.py`, `main.py`, `prometheus.yml` |
| 2026-07-07–09 | 2–4 | Migrated Chroma → Supabase pgvector. Built `PGVector` custom SQLAlchemy type with `bind_processor`/`result_processor`. | `models.py`, `chroma_client.py`, `searcher.py` |
| 2026-07-09–10 | 5–7 | Migrated embeddings HuggingFace/Gemini → AWS Bedrock Titan V2. Added `MatryoshkaBedrockEmbeddings` (512 dim). Boto3 bearer token auth (ABSK key). | `chroma_client.py`, `requirements.txt`, `config.py` |
| 2026-07-10 | 8 | Fixed SQLAlchemy `::vector` cast syntax → `CAST()`. Fixed null byte crash in PDF extraction. Verified full ingestion of 5 papers. | `searcher.py`, `pipeline.py` |
| 2026-07-11 | 9 | chunk_size 500→1500, overlap 50→150. Added `pdf_url` to papers table. Fixed `retrieve_papers` async bug. Removed hard domain filter from SQL. Discussed hybrid search plan. Updated this status doc. | `pipeline.py`, `nodes.py`, `searcher.py`, `ARXIVAI_STATUS.md` |

---

## 🔖 KEY DECISIONS LOG

| Date | Decision | Reason |
|:---|:---|:---|
| 2026-07-07 | Supabase pgvector instead of Chroma | Chroma had persistent metadata crashes; Supabase managed DB is simpler |
| 2026-07-07 | Single `src/models.py` for all 13 tables | Easier to manage FK relationships, avoids circular imports |
| 2026-07-09 | AWS Bedrock Titan V2 for embeddings | Free cloud model, no GPU needed, 512-dim Matryoshka, bearer token auth works on student account |
| 2026-07-09 | Groq as primary LLM (not Ollama) | Student machine cannot run 7B+ models locally; Groq free tier is sufficient |
| 2026-07-10 | chunk_size=1500, overlap=150 | 500-char chunks fragment academic paragraphs. 1500 chars ≈ 1 full paragraph → better retrieval. 5 papers = ~275 rows vs 800 rows |
| 2026-07-10 | `pdf_url` stored in `papers` table | Was missing from `Paper` record creation; needed for frontend display |
| 2026-07-10 | Domain NOT used as hard SQL filter | Domain classifier misclassifies often (Systems → NLP). Hard filter returns 0 results. Vector similarity is the real relevance signal |
| 2026-07-11 | Hybrid search: two-lane parallel | Restore domain as a soft signal/boost without making it a hard gate |
| — | RAGAS on-demand only | Cost and latency — Prometheus handles continuous monitoring |
| — | All agent nodes in single `nodes.py` | Reduced import complexity, easier to trace the full pipeline |

---

## 🚫 WHAT NOT TO DO

- Do NOT use SQLite — always Supabase PostgreSQL
- Do NOT use Chroma — we migrated fully to pgvector
- Do NOT call OpenAI API — use Groq/OpenRouter/Gemini in that order
- Do NOT use `::vector` or `::uuid` cast syntax in SQLAlchemy `text()` — use `CAST(:param AS vector)` instead
- Do NOT store PDFs in PostgreSQL — S3/local volume only
- Do NOT run RAGAS on every query — on-demand only
- Do NOT put auth logic in routers — it goes in `auth/service.py`
- Do NOT hardcode API keys anywhere — always `.env` + `config.py`
- Do NOT skip docstrings or type hints
- Do NOT use `def` for functions that call async DB or embedding functions — always `async def` + `await`
- Do NOT use domain as a hard SQL WHERE filter in vector search — use it as a soft boost only (hybrid search)
- Do NOT store null bytes (`\x00`) in text fields — strip them from PDF-extracted text before storing

