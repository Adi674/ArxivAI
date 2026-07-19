# ArxivAI v3.0 — Project Status Tracker

Paste this file into any AI assistant at session start for full context.
Format: ✅ Done | 🔄 In Progress | ⬜ Not Started | ❌ Blocked | ⚠️ Changed from original plan

**Last updated:** 2026-07-17
**Current focus:** v3.0 Enterprise Upgrade — planning complete, ready to implement Phase 1
**Sessions completed:** ~12+

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

### v2.0 Completed Work
```
Foundation & DB Setup        ████████████████████  100% ✅
Embeddings & Ingestion       ████████████████████  100% ✅ (AWS Bedrock)
Vector Search (Basic)        ████████████████████  100% ✅ (pgvector)
LangGraph 7-Agent Pipeline   ████████████████░░░░   80% 🔄
Auth & User System           ████████████████████  100% ✅
Papers CRUD                  ████████░░░░░░░░░░░░   40% 🔄
Collaboration System         ████░░░░░░░░░░░░░░░░   20% 🔄
Monitoring (Prometheus)      ████████████████░░░░   80% ✅
Deployment (Docker local)    ████████████████████  100% ✅
```

### v3.0 Enterprise Upgrade (new work)
```
Phase 1  — Hybrid Search (BM25+RRF+CrossEnc)  ████████████████████ 100% ✅
Phase 2  — LLM Eval (7-metric judge + NLI)    ████████████████████ 100% ✅
Phase 3  — Retrieval Metrics (Prometheus)      ████████████████████ 100% ✅
Phase 4  — Guardrail Agents (input+output)     ████████████████████ 100% ✅
Phase 5  — Intent Classifier + Convo Node      ████████████████████ 100% ✅
Phase 6  — Semantic Cache (Redis Cloud)        ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 7  — arXiv Live Fetch (Async SSE)        ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 8  — Circuit Breaker + structlog         ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 9  — OTel Distributed Tracing (Jaeger)  ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 10 — Celery Async Ingestion              ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 11 — Enterprise Patterns (5 items)       ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 12 — Kubernetes (k3s on AWS EC2)         ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 13 — Rename chroma_client.py             ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 14 — Complete Papers/Collab CRUD         ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 15 — Citation Graph (PostgreSQL)         ░░░░░░░░░░░░░░░░░░░░   0% ⬜
Phase 16 — Neo4j GraphRAG (future, ≥500 papers)░░░░░░░░░░░░░░░░░░░░   0% ⬜
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

## 🔄 v3.0 ENTERPRISE UPGRADE — PLANNED WORK (16 Phases)

> Full detailed plan lives in `implementation_plan.md` (AI artifact).
> Follow phases IN ORDER — each builds on the previous.

---

### Phase 1 — Hybrid Search + BM25 + RRF + Cross-Encoder Reranking ⬜

**Goal:** Replace single `semantic_search()` with a 3-stage retrieval pipeline.

```
semantic_search(k=20) ──┐
                         ├──► RRF merge(k=40) ──► cross-encoder rerank ──► top-5
bm25_search(k=20)     ──┘
```

- **BM25**: In-memory `rank_bm25` — built at startup from all `paper_chunks`, ~50MB RAM. Rebuilt on new ingestion.
- **RRF formula**: `score = Σ 1/(60 + rank_i)` with standard k=60 constant.
- **Cross-encoder**: `cross-encoder/ms-marco-MiniLM-L-6-v2` — 14MB, CPU-only, ~150ms, lazy-loaded singleton.

**New files:** `src/vectordb/bm25_index.py`, `src/vectordb/reranker.py`
**Modified:** `searcher.py`, `nodes.py`, `state.py`
**New deps:** `rank-bm25>=0.2.2`, `sentence-transformers>=2.6.0`
**Expected gain:** 10–15% precision improvement, negligible extra latency.

---

### Phase 2 — LLM Evaluation Upgrade (Agent 7) ⬜

**Goal:** Replace unreliable LLM self-check with proper multi-metric evaluation.

#### 2A — 7-Metric LLM-as-Judge (parallel evaluation)

| Metric | Weight | Alert if |
|---|---|---|
| Faithfulness | 0.25 | < 0.70 |
| Answer Relevancy | 0.20 | < 0.65 |
| Context Recall | 0.15 | < 0.60 |
| Coherence | 0.15 | < 0.70 |
| Context Precision | 0.15 | < 0.50 |
| Citation Accuracy | 0.10 | < 0.80 |

Each metric gets its own prompt with chain-of-thought reasoning + evidence quote + numeric score.
Judge model: `llama-3.3-70b-versatile`. Feedback strings → fed into `SYNTHESIS_REFINE_PROMPT`.

#### 2B — NLI Hallucination Detection

Model: `cross-encoder/nli-deberta-v3-small` (CPU, ~200ms, lazy-loaded singleton).
Per sentence: if `max_entailment_score < 0.5` across all source chunks → flagged as unsupported.
Returns: `hallucination_rate`, `attribution_map {sentence → paper_id}`, `unsupported_claims`.

**New files:** `src/eval/llm_judge.py`, `src/eval/hallucination.py`, `src/eval/metrics.py`
**Modified:** `prompts.py` (+7 eval prompts), `nodes.py` (replace evaluate_answer), `state.py`

---

### Phase 3 — Retrieval Quality Metrics (Prometheus) ⬜

**Goal:** System-level Precision@5, Recall@5, MRR, NDCG@5 per domain in Prometheus/Grafana.

**Ground truth (3-tier):**
1. Weekly Celery task — LLM-as-judge labels 5% of past queries
2. User thumbs up/down on sources → `UserFeedback` table
3. Citation graph — if A cites B, B is relevant for A-topic queries

**New Prometheus metrics:**
`retrieval_precision_at5`, `retrieval_recall_at5`, `retrieval_mrr`, `retrieval_ndcg_at5`,
`hallucination_rate_hist`, `eval_score_hist`, `cache_hits_total`, `cache_misses_total`,
`arxiv_fallback_total`, `guardrail_blocks_total`, `intent_classification_total`, `circuit_breaker_state`

**New files:** `src/eval/retrieval_metrics.py`, `src/eval/feedback.py`, `src/worker/eval_tasks.py`
**Modified:** `main.py` (+new Prometheus metrics), `models.py` (+UserFeedback table, +EvalResult table)

---

### Phase 4 — Guardrail Agents (Input + Output) ⬜

**Goal:** Safety gate before pipeline runs. Every query must pass through Agent 0.

#### Agent 0: Input Guardrail (5-check pipeline, fail-fast)
```
1. Rate limit check        → Redis sliding window, 429 + Retry-After
2. Scope pre-filter        → regex, ~1ms, blocks obvious OOS without LLM call
3. Toxicity + Jailbreak    → Groq llama-3.1-8b-instant, structured JSON, ~300ms
4. PII detection           → presidio-analyzer (local), strips phone/SSN/email, ~50ms
5. Domain confidence gate  → if domain_confidence < 0.35 → polite decline, skip pipeline
```
Output: `GuardrailResult {allowed, reason, cleaned_query, risk_score, pii_found}`

#### Agent 8 (new): Output Guardrail
PII strip on answer + harmful content check + citation verify (all `[paper_id]` must exist in retrieved_papers) + length check (>4000 tokens → truncate).

**New files:** `src/guardrails/__init__.py`, `input_guard.py`, `output_guard.py`, `pii_detector.py`, `rate_limiter.py`
**Modified:** `graph.py` (prepend input guard, append output guard), `state.py`
**New deps:** `presidio-analyzer>=2.2.0`, `presidio-anonymizer>=2.2.0`, `spacy>=3.7.0`

---

### Phase 5 — Intent Classifier + Conversational Node ⬜

**Goal:** Stop routing "hi", "thanks", "yes" through the full 7-agent pipeline.

**Intent categories:** `conversational` | `research` | `clarification` | `out_of_scope`
**Model:** `llama-3.1-8b-instant` (Groq) + last 5 messages as context. Decision in <300ms.

**Routing:**
- `research` → full RAG pipeline (current flow)
- `conversational` / `clarification` → ConversationalNode (single LLM call + history)
- `out_of_scope` → polite decline, no pipeline

**ConversationalNode:** Fetches last N messages from DB → single Groq call → logs to `messages` table.

**New files:** `src/agents/intent_classifier.py`, `src/agents/conversational_node.py`
**Modified:** `graph.py` (conditional entry routing), `state.py` (+intent, +is_conversational, +conversation_id), `query/service.py`

---

### Phase 6 — Semantic Cache (Redis Cloud + RediSearch) ⬜

**Goal:** Skip full pipeline for repeated or semantically similar queries.

**Redis structure:** RediSearch vector index (Structure 3 — KNN cosine search in Redis).
```
Each entry = Redis HASH:
  Key:    cache:{domain}:{md5(normalized_query)}
  Fields: vector (512-dim float32 bytes packed), answer, sources (JSON),
          eval_scores (JSON), domain, created_at, ttl_expires

RediSearch index:
  FT.CREATE cache_idx ON HASH PREFIX 1 cache:
    SCHEMA vector VECTOR FLAT 6 TYPE FLOAT32 DIM 512 DISTANCE_METRIC COSINE
```

**Lookup:** `FT.SEARCH ... KNN 1` → HIT if `cosine_score >= 0.92` AND TTL not expired.

**TTL by domain:** Math/Theory/Physics → 3600s | Systems/Robotics → 1800s | ML/GenAI/NLP/CV → 900s

**Cache invalidation:** Per-domain when new papers ingested in that domain.

> ⚠️ Requires Redis Cloud credentials — provide `REDIS_CLOUD_URL` + `REDIS_CLOUD_PASSWORD` when starting this phase.

**New files:** `src/cache/__init__.py`, `src/cache/semantic_cache.py`, `src/cache/redis_client.py`
**Modified:** `config.py` (+REDIS_CLOUD_URL, +CACHE_SIMILARITY_THRESHOLD=0.92, +CACHE_TTL_*), `query/service.py`

---

### Phase 7 — arXiv Live Fetch Fallback (Async SSE) ⬜

**Goal:** When retrieval relevance < 0.35, fetch from arXiv in background instead of returning empty/hallucinated answer.

**Trigger:** In `retrieve_papers()` after hybrid search: `if max_rerank_score < 0.35 → trigger Celery task`

**Async flow:**
```
1. System immediately responds:
   "No papers found. Searching arXiv... (20-30 seconds)"
2. Celery background task:
   → arxiv_fetcher.live_search(query, n=3) → arXiv API
   → Download top-3 PDFs → ingest_pipeline.run() → chunk → embed → pgvector
   → Rebuild BM25 index → paper.status = "ready"
   → Push SSE: {type: "arxiv_fetch_complete", papers: [...], auto_requery: true}
3. Client auto-resubmits original query → now gets real results
```

**New files:** `src/worker/arxiv_tasks.py`
**Modified:** `arxiv_fetcher.py` (+live_search_and_fetch), `nodes.py` (fallback trigger), `query/router.py` (SSE endpoint GET /api/query/stream/{conversation_id})

---

### Phase 8 — LLM Reliability (Circuit Breaker + Structured Logging) ⬜

#### Circuit Breaker (`pybreaker`)
```
Groq:        fail_max=3, reset_timeout=60s
OpenRouter:  fail_max=3, reset_timeout=90s
Gemini:      fail_max=5, reset_timeout=120s
When OPEN: immediately skip to next provider (no timeout wait)
```

#### Structured Logging (`structlog`)
Replace all `logger.info(f"...")` with machine-parseable JSON:
```python
log.info("domain_classified", domain=domain, confidence=0.87, latency_ms=142, user_id=uid)
```
Enables Loki queries: `domain="ML" AND confidence < 0.5` across millions of events.

**New files:** `src/llm/circuit_breaker.py`, `src/core/logging.py`
**Modified:** `provider.py` (wrap each provider), all files using `logging.getLogger()`
**New deps:** `pybreaker>=1.0.1`, `structlog>=24.1.0`

---

### Phase 9 — OpenTelemetry Distributed Tracing (Jaeger) ⬜

**Goal:** Per-agent latency waterfall. Know exactly which agent is the bottleneck.

```
trace: query_abc123 (total: 2.1s)
  ├─ span: input_guardrail          12ms
  ├─ span: intent_classification    95ms
  ├─ span: cache_lookup              8ms
  ├─ span: domain_classify         310ms
  ├─ span: hybrid_retrieve         420ms   ← bottleneck visible
  │    ├─ semantic_search          180ms
  │    ├─ bm25_search               45ms
  │    └─ cross_enc_rerank         195ms
  ├─ span: reason_over_papers     1200ms
  ├─ span: synthesize_answer      1800ms
  └─ span: evaluate_answer         380ms
```

Backend: **Jaeger** (add to docker-compose, free open-source).

**New files:** `src/core/tracing.py` — OTel setup + `@trace_span("name")` decorator
**Modified:** `nodes.py` (decorate each node), `docker-compose.yaml` (add Jaeger)
**New deps:** `opentelemetry-sdk>=1.23.0`, `opentelemetry-instrumentation-fastapi>=0.44b0`, `opentelemetry-exporter-otlp>=1.23.0`

---

### Phase 10 — Celery Async Paper Ingestion ⬜

**Goal:** Non-blocking paper upload. Current flow blocks for 15–60s.

```
Current:  POST /papers/upload → inline ingestion → 60s response → timeout risk
Upgraded: POST /papers/upload → save metadata → 201 immediately
                                    → Celery task (Redis Cloud broker)
                                    → Worker: extract→chunk→embed→store
                                    → paper.status: pending→processing→ready|failed
User: GET /papers/{id}/status  OR  SSE push when ready
```

**New files:** `src/worker/celery_app.py`, `src/worker/tasks.py`
**Modified:** `models.py` (+Paper.status field), `papers/service.py` (queue task), `papers/router.py` (+status endpoint)
**New deps:** `celery>=5.3.6`, `redis[hiredis]>=5.0.0`

---

### Phase 11 — Enterprise Patterns (5 items) ⬜

#### A — Query Confidence Gating
If `domain_confidence < 0.35` after classify → polite decline, skip 5 LLM calls, save cost.

#### B — Multi-hop Query Decomposition
When `query_type == "multi_hop"` (already detected): parallel `hybrid_search()` per sub-query → merge + rerank.

#### C — Answer Confidence Bounds
Return `{confidence: {overall, lower, upper, grounded_claims, ungrounded_claims}}` in API response.

#### D — UserMemory Activation
`UserMemory` model exists in `models.py` but unused. Wire up: update domain interest weights per query, bias domain classifier prompt with user's top-3 domains.

#### E — Sliding Window Rate Limiting
Redis per-user per-minute counter. Returns `Retry-After` header on 429. Limits: 10/min free, 30/min premium.

---

### Phase 12 — Kubernetes (k3s on AWS EC2) ⬜

**Goal:** Self-managed K8s for deep learning + strong resume value.

**Setup:**
```
2 × AWS t2.micro EC2 (free tier, 1 vCPU / 1GB RAM):
  Node 1: Control plane (k3s server) — API server, etcd, scheduler (~500MB RAM)
  Node 2: Worker node (k3s agent)    — runs application pods

Why k3s over kubeadm:
  kubeadm needs ~1.5GB RAM for control plane → exceeds t2.micro limit
  k3s uses ~500MB → fits comfortably
  k3s is production-grade (CNCF member, used by Rancher) → fully valid for resume
```

**K8s manifests to create:**
```
k8s/
├── namespace.yaml
├── configmap.yaml           non-secret env vars
├── secrets.yaml             API keys (base64-encoded)
├── api-deployment.yaml      FastAPI, 2 replicas
├── api-service.yaml
├── celery-deployment.yaml   Celery worker, 1–3 replicas
├── ingress.yaml             Nginx Ingress
├── monitoring/
│   ├── prometheus.yaml
│   ├── grafana.yaml
│   └── jaeger.yaml
└── hpa/
    ├── api-hpa.yaml         min=2, max=10, target CPU=70%
    └── celery-hpa.yaml      min=1, max=5
```

**Resume bullets this earns:**
- "Deployed on self-managed Kubernetes (k3s) on AWS EC2 with HPA"
- "Semantic cache on Redis Cloud RediSearch (~40% cache hit rate)"
- "End-to-end observability: Prometheus + Grafana + OpenTelemetry/Jaeger"

---

### Phase 13 — Rename `chroma_client.py` → `embeddings_client.py` ⬜

File is purely an AWS Bedrock embedding client. Rename for clarity. Update all import references across the codebase.

---

### Phase 14 — Complete Papers CRUD + Collaboration ⬜

- Complete `papers/service.py` upload flow (uses Celery from Phase 10)
- Complete collaboration apply/approve flow in `collaboration/service.py`
- Add `GET /papers/{id}/status` endpoint

---

### Phase 15 — Citation Graph (PostgreSQL) ⬜

**Goal:** Parse references from ingested PDFs. Build citation relationships in Supabase.
Use SQL for now — migrate to Neo4j in Phase 16 when corpus grows.

```sql
citation_edges (
  citing_paper_id  TEXT REFERENCES papers(paper_id),
  cited_paper_id   TEXT REFERENCES papers(paper_id),
  cited_arxiv_id   TEXT,
  context_quote    TEXT,
  PRIMARY KEY (citing_paper_id, cited_paper_id)
)
```

**What this enables even in SQL:** "Papers citing X" feature, weak supervision for retrieval eval,
basic citation-count boosted reranking.

**New files:** `src/graphdb/citation_sql.py` (add_citation, get_citations, get_cited_by)
**Modified:** `models.py` (+CitationEdge model), `ingestion/pipeline.py` (parse References section, write edges)

---

### Phase 16 — Neo4j GraphRAG (Future — requires ≥500 papers in corpus) ⬜

> ⚠️ **Do NOT start until Phase 15 is working AND corpus has ≥500 papers.**
> Graph traversal provides no meaningful value at small scale.
> PostgreSQL citation_edges table is the placeholder. Migration is clean — only storage layer changes.

**Why a Graph DB for citations (not just a SQL table):**
- Multi-hop traversal: SQL recursive CTEs slow exponentially at 3+ hops. Graph DBs use pointer-chasing — milliseconds at any depth.
- PageRank, community detection, shortest path — built-in Graph Data Science library in Neo4j.
- This is exactly **Microsoft's GraphRAG** pattern (published 2024, now industry standard for RAG).

**Graph schema:**
```
Nodes:          (:Paper), (:Author), (:Topic), (:Venue)
Relationships:  (Paper)-[:CITES {context_quote}]->(Paper)
                (Paper)-[:WRITTEN_BY {author_order}]->(Author)
                (Paper)-[:COVERS]->(Topic)
                (Author)-[:CO_AUTHORED_WITH {paper_count}]->(Author)
```

**Cypher queries this enables:**
```cypher
-- 2-hop citation neighborhood (instant vs. slow recursive SQL)
MATCH (p:Paper {paper_id: $id})-[:CITES*1..2]-(related:Paper)
RETURN DISTINCT related

-- Most influential papers in corpus (PageRank)
CALL gds.pageRank.stream('citation-graph') YIELD nodeId, score

-- Citation path between two papers
MATCH path = shortestPath((p1:Paper)-[:CITES*]-(p2:Paper)) RETURN path

-- Papers in same research cluster (community detection)
CALL gds.louvain.stream('citation-graph') YIELD nodeId, communityId
```

**Graph expansion in retrieval pipeline:**
```
hybrid_search(query) → top-5
    ↓ Neo4j 1-hop expansion
top-5 + papers_citing_them + papers_they_cite (deduplicated)
    ↓ cross-encoder rerank expanded set
final top-5 (higher recall, more comprehensive coverage)
```

**Chosen service:** **Neo4j AuraDB Free Tier** — 200k nodes, 400k relationships,
cloud-managed (no Docker container), connection string like Supabase, Cypher is industry-standard GQL.

**Migration from Phase 15:** `citation_sql.py` → swap backend in `citation_graph.py`.
All reference parsing logic in `pipeline.py` stays exactly the same.

**New files (Phase 16 only):**
- `src/graphdb/__init__.py`
- `src/graphdb/neo4j_client.py` — driver connection, session factory
- `src/graphdb/citation_graph.py` — replaces citation_sql.py backend
- `src/graphdb/graph_expander.py` — `expand_retrieved_papers()` post-retrieval graph expansion

**Modified (Phase 16 only):**
- `nodes.py` — `retrieve_papers()` calls graph_expander after hybrid search
- `nodes.py` — `reason_over_papers()` uses real Cypher (replaces LLM-fabricated citation_graph dict)
- `config.py` — `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `docker-compose.yaml` — add Neo4j service for local dev
- `k8s/` — add Neo4j StatefulSet + PersistentVolumeClaim

**New dep (Phase 16 only):** `neo4j>=5.0.0`

---

### Automated Tests (add alongside each phase)

```
tests/
├── test_hybrid_search.py       precision comparison vs. semantic-only
├── test_reranker.py            known relevant vs. irrelevant docs
├── test_llm_judge.py           golden test cases with known hallucinated answers
├── test_nli_attribution.py     sentence-level entailment on known pairs
├── test_intent_classifier.py   50 example queries with expected intent labels
├── test_guardrails.py          toxic/jailbreak/PII/OOS test cases
├── test_semantic_cache.py      hit/miss on similar/dissimilar queries
└── test_circuit_breaker.py     simulate provider failure, verify failover
```

---

## 📝 SESSION LOG

| Date | Session # | What was done | Files changed |
|:---|:---|:---|:---|
| 2026-07-07 | 1 | Initial setup, Supabase connection, arXiv fetcher, Chroma crash debugging | `pipeline.py`, `arxiv_fetcher.py`, `main.py`, `prometheus.yml` |
| 2026-07-07–09 | 2–4 | Migrated Chroma → Supabase pgvector. Built `PGVector` custom SQLAlchemy type with `bind_processor`/`result_processor`. | `models.py`, `chroma_client.py`, `searcher.py` |
| 2026-07-09–10 | 5–7 | Migrated embeddings HuggingFace/Gemini → AWS Bedrock Titan V2. Added `MatryoshkaBedrockEmbeddings` (512 dim). Boto3 bearer token auth (ABSK key). | `chroma_client.py`, `requirements.txt`, `config.py` |
| 2026-07-10 | 8 | Fixed SQLAlchemy `::vector` cast syntax → `CAST()`. Fixed null byte crash in PDF extraction. Verified full ingestion of 5 papers. | `searcher.py`, `pipeline.py` |
| 2026-07-11 | 9 | chunk_size 500→1500, overlap 50→150. Added `pdf_url` to papers table. Fixed `retrieve_papers` async bug. Removed hard domain filter from SQL. Discussed hybrid search plan. | `pipeline.py`, `nodes.py`, `searcher.py`, `ARXIVAI_STATUS.md` |
| 2026-07-17 | 10–12 | v3.0 enterprise upgrade planning. Full 16-phase roadmap designed and documented. All architectural decisions finalized: hybrid search (BM25+RRF+CrossEncoder), 7-metric LLM-as-Judge evaluation, NLI hallucination detection, guardrail agents (Agent 0 + Agent 8), intent classifier (Agent 1) with conversational routing, Redis Cloud RediSearch semantic cache, arXiv async fallback with SSE, circuit breakers, OTel/Jaeger tracing, Celery async ingestion, k3s on AWS EC2, citation graph (SQL→Neo4j migration path), GraphRAG (Phase 16 future). | `ARXIVAI_STATUS.md` |

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
| 2026-07-17 | BM25: in-memory rank_bm25 (not Elasticsearch) | No new service, fits current scale (<100k chunks), rebuild on new ingestion event |
| 2026-07-17 | Redis Cloud + RediSearch KNN vector index for cache | FT.SEARCH KNN cosine similarity search directly in Redis — no Python similarity loop, sub-millisecond lookup |
| 2026-07-17 | Guardrails: Groq LLM prompt (not Llama-Guard model) | Same infrastructure, structured JSON prompt output, no extra model file or service to manage |
| 2026-07-17 | Kubernetes: k3s on AWS EC2 t2.micro (not managed EKS) | EKS costs ~$72/month; k3s on free-tier EC2 achieves the same K8s learning objectives at zero cost |
| 2026-07-17 | arXiv live fetch: async Celery + SSE notification (not sync) | 30s synchronous wait is poor UX; immediate partial response + background ingest + SSE notification is far better |
| 2026-07-17 | LLM evaluation: custom 7-metric judge (not RAGAS library) | RAGAS adds heavy dependency; custom prompts give more control and domain-specific metric tuning |
| 2026-07-17 | Citation graph: PostgreSQL first (Phase 15), Neo4j AuraDB later (Phase 16) | Graph traversal irrelevant at <100 papers; SQL placeholder now, clean migration when corpus grows to 500+ |
| 2026-07-17 | Cross-encoder reranker: ms-marco-MiniLM-L-6-v2 | 14MB, CPU-only, ~150ms for top-40 pairs, no GPU, lazy-loaded singleton |
| 2026-07-17 | NLI hallucination check: nli-deberta-v3-small | Deterministic classifier (not probabilistic), sentence-level attribution, CPU ~200ms, complements LLM judge score |
| 2026-07-17 | Guardrail PII: presidio-analyzer (local, not cloud) | Runs in-process, no API call, no data leaving the system for PII processing, ~50ms |
| 2026-07-17 | Discussed Neo4j GraphRAG for citation graph | Graph DBs give multi-hop traversal + PageRank not possible in SQL; deferred to Phase 16 until corpus is large enough |

---

## 🚫 WHAT NOT TO DO

### v2.0 Rules (still apply)
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

### v3.0 Rules (new)
- Do NOT use LLM self-evaluation for hallucination — LLMs grade their own outputs leniently; use NLI + separate judge LLM
- Do NOT use Elasticsearch/OpenSearch for BM25 — in-memory rank_bm25 is sufficient at current scale, no new service needed
- Do NOT start Neo4j (Phase 16) until corpus has ≥500 papers — graph traversal adds no value at small corpus size
- Do NOT use managed EKS/GKE for Kubernetes — self-managed k3s on free-tier EC2 gives better learning + zero cost
- Do NOT route conversational queries through full RAG pipeline — intent classifier must run first and route to ConversationalNode
- Do NOT rebuild BM25 index on every query — build once at startup, invalidate + rebuild only when new papers are ingested
- Do NOT store cache vectors as plain strings — pack as float32 bytes with `struct.pack("512f", *vector)` for RediSearch KNN
- Do NOT skip the output guardrail — synthesized answers can echo PII that appeared in query context
- Do NOT send LLM provider requests without a circuit breaker — one provider outage should not cascade to 30s timeouts
- Do NOT implement Neo4j before PostgreSQL citation_edges (Phase 15) — the SQL layer validates reference parsing logic first
- Do NOT skip tests alongside each phase — add the corresponding test file before moving to the next phase

