# ArxivAI v2.0 — Project Status Tracker

This file tracks every file, function, and feature in the project. Update after every working session. Paste into Claude at session start for full context. Format: ✅ Done | 🔄 In Progress | ⬜ Not Started | ❌ Blocked

---

## 📊 OVERALL PROGRESS

Week 1 — Foundation          ░░░░░░░░░░  0%

Week 2 — Domain Routing      ░░░░░░░░░░  0%

Week 3 — Parallel Agents     ░░░░░░░░░░  0%

Week 4 — User Features       ░░░░░░░░░░  0%

**Last updated:** \[date\] **Current focus:** Week 1 — Foundation **Sessions completed:** 0

---

## 🗂️ WEEK 1 — FOUNDATION

### Project Setup

| Status | Task |
| :---- | :---- |
| ⬜ | Create GitHub repository |
| ✅ | Set up folder structure (`src/`, `tests/`, `scripts/`, `docker/`) |
| ✅ | Create `requirements.txt` |
| ⬜ | Create `.env.example` |
| ✅ | Create `docker-compose.yml` (FastAPI \+ PostgreSQL \+ Chroma \+ Prometheus \+ Grafana) |
| ✅ | Create `Dockerfile` |
| ⬜ | Verify Ollama running locally with Mistral-7B |

---

### `src/config.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**Functions / Variables:**

| Status | Name | Type | Description |
| :---- | :---- | :---- | :---- |
| ✅ | `Settings` | Pydantic BaseSettings class | Loads all env vars. Fields: `DATABASE_URL`, `CHROMA_PATH`, `JWT_SECRET`, `JWT_EXPIRE_HOURS`, `OLLAMA_BASE_URL`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `S3_BUCKET`, `S3_ENDPOINT`, `ARXIV_CATEGORIES`, `DEFAULT_LLM_MODE` |
| ✅ | `get_settings()` | function → Settings | Cached singleton. Returns the Settings instance. Called everywhere config is needed. |

---

### `src/database.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ✅ | `get_engine()` | none | `Engine` | Creates SQLAlchemy engine from `DATABASE_URL`. Called once at startup. |
| ✅ | `get_session()` | none | `AsyncSession` | FastAPI dependency. Yields an async DB session. Used in all routers via `Depends(get_session)`. |
| ✅ | `create_all_tables()` | none | none | Creates all tables from models. Called at app startup in `main.py`. |

---

### `src/main.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**What it does:** FastAPI app entry point. Registers all routers, runs `create_all_tables()` on startup, mounts Prometheus metrics endpoint at `/metrics`, sets up CORS.

**Routers registered:**

| Status | Prefix | Module |
| :---- | :---- | :---- |
| ✅ | `/auth` | `src/auth/router.py` |
| ✅ | `/papers` | `src/papers/router.py` |
| ✅ | `/query` | `src/query/router.py` |
| ✅ | `/collaboration` | `src/collaboration/router.py` |
| ✅ | `/metrics` | Prometheus ASGI handler |

---

### `src/auth/`

#### `src/auth/models.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Models:**

| Status | Model | Table | Fields | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `User` | `users` | `id (UUID PK)`, `email (unique)`, `hashed_password`, `full_name`, `domains (array)`, `organization`, `is_active`, `created_at` | Main user table. `domains` stores list of research domains user works in. |

---

#### `src/auth/schemas.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Schemas:**

| Status | Schema | Fields | Used For |
| :---- | :---- | :---- | :---- |
| ⬜ | `UserRegister` | `email`, `password`, `full_name`, `domains[]` | POST /auth/register request body |
| ⬜ | `UserLogin` | `email`, `password` | POST /auth/login request body |
| ⬜ | `UserOut` | `id`, `email`, `full_name`, `domains`, `created_at` | Response schema (no password) |
| ⬜ | `TokenOut` | `access_token`, `token_type` | Login response |

---

#### `src/auth/service.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `hash_password()` | `password: str` | `str` | Hashes plain password using bcrypt. Returns hashed string. |
| ⬜ | `verify_password()` | `plain: str`, `hashed: str` | `bool` | Compares plain password against stored hash. Returns True if match. |
| ⬜ | `create_access_token()` | `user_id: str`, `expires_delta: timedelta` | `str` | Creates signed JWT token with user\_id in payload. Expiry from config. |
| ⬜ | `decode_token()` | `token: str` | `dict` | Decodes JWT, validates signature, returns payload. Raises 401 if invalid/expired. |
| ⬜ | `get_current_user()` | `token: str` (from header), `db: AsyncSession` | `User` | FastAPI dependency. Decodes token, fetches user from DB. Used in all protected routes. |
| ⬜ | `register_user()` | `data: UserRegister`, `db: AsyncSession` | `User` | Checks email not taken, hashes password, creates User record, returns user. |
| ⬜ | `login_user()` | `data: UserLogin`, `db: AsyncSession` | `TokenOut` | Verifies email \+ password, returns JWT token. Raises 401 if wrong credentials. |

---

#### `src/auth/router.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Endpoints:**

| Status | Method | Path | Auth | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | POST | `/auth/register` | None | Register new user. Body: `UserRegister`. Returns `UserOut`. |
| ⬜ | POST | `/auth/login` | None | Login. Body: `UserLogin`. Returns `TokenOut` with JWT. |
| ⬜ | GET | `/auth/me` | JWT required | Returns current user profile (`UserOut`). |

---

### `src/ingestion/`

#### `src/ingestion/arxiv_fetcher.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ✅ | `fetch_paper_metadata()` | `category: str`, `num_papers: int`, `date_from: str` | `list[dict]` | Calls arXiv API, parses XML response. Returns list of `{id, title, authors, summary, pdf_url, categories}` dicts. |
| ✅ | `download_pdf()` | `paper_id: str`, `pdf_url: str`, `output_dir: str` | `str | None` | Downloads single PDF. Returns local file path on success, None on failure. Skips if already downloaded. |
| ⬜ | `batch_download_pdfs()` | `papers: list[dict]`, `output_dir: str`, `max_workers: int` | `dict[str, str]` | Downloads all PDFs in parallel using ThreadPoolExecutor. Returns `{paper_id: file_path}` map. |
| ✅ | `fetch_fresh_papers()` | `query: str`, `domain: str`, `k: int` | `list[dict]` | Called by Retriever agent when arXiv baseline is insufficient. Fetches k fresh papers matching query. Returns metadata list ready for ingestion. |

---

#### `src/ingestion/pdf_extractor.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `extract_text_from_pdf()` | `pdf_path: str` | `str | None` | Uses PyPDF2 to extract raw text from PDF. Cleans whitespace. Returns text string or None if extraction fails. |
| ⬜ | `extract_all_pdfs()` | `pdf_dir: str` | `dict[str, str]` | Extracts text from all PDFs in directory. Returns `{paper_id: extracted_text}`. Skips failed extractions with warning log. |

---

#### `src/ingestion/chunker.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `chunk_text()` | `text: str`, `paper_id: str`, `metadata: dict` | `list[Document]` | Splits text using LangChain `RecursiveCharacterTextSplitter` (chunk\_size=500, overlap=50). Returns list of LangChain `Document` objects with metadata attached to each chunk. |
| ⬜ | `chunk_all_papers()` | `papers_text: dict[str, str]`, `metadata_map: dict` | `list[Document]` | Chunks all papers. Returns flat list of all Document chunks across all papers. |

---

#### `src/ingestion/embedder.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `get_embedding_model()` | none | `HuggingFaceEmbeddings` | Loads `all-MiniLM-L6-v2` from HuggingFace. Cached singleton — only loads once. |
| ⬜ | `embed_and_store()` | `documents: list[Document]`, `vectorstore: Chroma` | `int` | Embeds list of Document chunks and adds to Chroma. Returns count of documents added. |

---

#### `src/ingestion/pipeline.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ✅ | `run_arxiv_ingestion()` | `category: str`, `num_papers: int` | `dict` | Full pipeline: fetch metadata → download PDFs → extract text → chunk → embed → store in Chroma. Returns `{total_papers, total_chunks, failed}` summary. |
| ⬜ | `ingest_user_paper()` | `pdf_path: str`, `paper_metadata: dict`, `user_id: str` | `dict` | Ingests a single user-uploaded paper. Same pipeline as arXiv but with user metadata. Called as background task. Returns `{paper_id, chunks_created, status}`. |

---

### `src/vectordb/`

#### `src/vectordb/chroma_client.py`

| Status | Item |
| :---- | :---- |
| ✅ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ✅ | `get_chroma_client()` | none | `chromadb.Client` | Creates persistent Chroma client at path from config. Cached singleton. |
| ✅ | `get_vectorstore()` | none | `Chroma` | Returns LangChain Chroma wrapper with embedding model attached. Cached singleton. |

---

#### `src/vectordb/searcher.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `build_access_filter()` | `user_id: str`, `domain: str`, `collab_ids: list[str]` | `dict` | Builds Chroma `where` filter. Allows: user's private papers \+ all public papers \+ collaborative papers user belongs to. All scoped to given domain. |
| ⬜ | `semantic_search()` | `query: str`, `user_id: str`, `domain: str`, `k: int`, `collab_ids: list[str]` | `list[dict]` | Runs vector search with access filter. Returns list of `{paper_id, title, content, relevance_score, source, visibility}`. |
| ⬜ | `search_private_only()` | `query: str`, `user_id: str`, `domain: str`, `k: int` | `list[dict]` | Searches only user's private papers. Used when query explicitly targets personal papers. |
| ⬜ | `calculate_avg_relevance()` | `results: list[dict]` | `float` | Averages relevance scores across results. Retriever agent uses this to decide if reformulation is needed. |

---

## 🗂️ WEEK 2 — DOMAIN ROUTING

### `src/agents/state.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**What it does:** Defines `RAGState` TypedDict — the single shared state object that all LangGraph agents read from and write to. Every field is documented below.

| Status | Field | Type | Set By | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `original_query` | str | Query router | The raw user query |
| ⬜ | `user_id` | str | Query router | ID of requesting user |
| ⬜ | `collab_ids` | list\[str\] | Query router | Collaboration IDs user belongs to |
| ⬜ | `llm_mode` | str | Query router | budget / balanced / quality / research |
| ⬜ | `primary_domain` | str | Domain classifier | Detected domain |
| ⬜ | `secondary_domains` | list\[str\] | Domain classifier | Secondary domains |
| ⬜ | `domain_confidence` | float | Domain classifier | Confidence score 0-1 |
| ⬜ | `query_type` | str | Query analyzer | single\_hop or multi\_hop |
| ⬜ | `sub_queries` | list\[str\] | Query analyzer | Broken sub-queries if multi\_hop |
| ⬜ | `needs_personal_papers` | bool | Query analyzer | True if query mentions own work |
| ⬜ | `needs_recent` | bool | Query analyzer | True if query has recency signal |
| ⬜ | `search_spaces` | list\[str\] | Search strategy | Which namespaces to search |
| ⬜ | `fetch_arxiv_fresh` | bool | Search strategy | Whether to pre-fetch from arXiv |
| ⬜ | `retrieved_papers` | list\[dict\] | Retriever | Papers retrieved with scores |
| ⬜ | `reformulation_count` | int | Retriever | How many times query was reformulated |
| ⬜ | `findings` | dict | Reasoner | Key findings per paper |
| ⬜ | `contradictions` | list\[dict\] | Reasoner | Conflicting claims between papers |
| ⬜ | `agreements` | list\[dict\] | Reasoner | Agreed-upon claims across papers |
| ⬜ | `citation_graph` | dict | Reasoner | Maps claim → supporting papers |
| ⬜ | `knowledge_gaps` | list\[str\] | Reasoner | What the papers don't cover |
| ⬜ | `draft_answer` | str | Synthesis | Generated answer with citations |
| ⬜ | `hallucination_detected` | bool | Evaluator | True if hallucination found |
| ⬜ | `quality_score` | float | Evaluator | Overall RAGAS quality score |
| ⬜ | `ragas_scores` | dict | Evaluator | All individual RAGAS metric scores |
| ⬜ | `needs_refinement` | bool | Evaluator | True if quality \< 0.7 |
| ⬜ | `refinement_count` | int | Evaluator | Loop counter — max 3 |
| ⬜ | `evaluator_feedback` | str | Evaluator | Specific feedback sent to Synthesis |
| ⬜ | `final_answer` | str | Format node | Cleaned final answer |
| ⬜ | `sources` | list\[dict\] | Format node | Source papers list for response |
| ⬜ | `reasoning_trace` | list\[str\] | Format node | Audit trail of agent decisions |

---

### `src/agents/domain_classifier.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `classify_domain()` | `state: RAGState` | `RAGState` | LangGraph node. Sends query to Mistral-7B via `provider.py`. Parses LLM output into domain \+ confidence. Updates `primary_domain`, `secondary_domains`, `domain_confidence` in state. |

---

### `src/agents/query_analyzer.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `analyze_query()` | `state: RAGState` | `RAGState` | LangGraph node. Detects single vs multi-hop, personal paper mentions, recency signals. Generates sub-queries if multi-hop. Updates state fields accordingly. |

---

### `src/agents/search_strategy.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `decide_search_strategy()` | `state: RAGState` | `RAGState` | LangGraph node. Checks which namespaces exist for user in identified domain. Decides search\_spaces list and whether to pre-fetch arXiv. Updates state. |

---

### `src/agents/retriever.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `retrieve_papers()` | `state: RAGState` | `RAGState` | LangGraph node. Searches each search\_space in parallel. Checks avg relevance. If \< 0.6 → calls reformulate. If still low → calls arxiv\_fetch. Updates `retrieved_papers` and `reformulation_count`. |
| ⬜ | `reformulate_query()` | `original_query: str`, `domain: str` | `str` | Uses Neural-Chat-7B to rewrite query for better retrieval. Returns reformulated query string. |

---

### `src/agents/reasoner.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `reason_over_papers()` | `state: RAGState` | `RAGState` | LangGraph node. Runs all analysis tools on retrieved papers using Llama2-13B. Updates `findings`, `contradictions`, `agreements`, `citation_graph`, `knowledge_gaps`. |

---

### `src/agents/synthesis.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `synthesize_answer()` | `state: RAGState` | `RAGState` | LangGraph node. Generates answer using Reasoner's analysis. If `evaluator_feedback` present in state, uses it to refine. Updates `draft_answer`. |

---

### `src/agents/evaluator.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `evaluate_answer()` | `state: RAGState` | `RAGState` | LangGraph node. Runs RAGAS checks on draft\_answer vs retrieved\_papers. Sets `quality_score`, `ragas_scores`, `hallucination_detected`, `needs_refinement`, `evaluator_feedback`. Increments `refinement_count`. |
| ⬜ | `should_refine()` | `state: RAGState` | `str` | LangGraph conditional edge function. Returns `"synthesis"` if needs\_refinement and refinement\_count \< 3, else returns `"format_output"`. |

---

### `src/agents/graph.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**What it does:** Builds and compiles the LangGraph `StateGraph`. Registers all 7 agent nodes, defines edges between them (sequential for Phase 1, async parallel for Phase 2), and adds conditional edge from evaluator to either synthesis or format\_output.

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `build_graph()` | none | `CompiledGraph` | Creates StateGraph(RAGState), adds all nodes, sets entry point to domain\_classifier, adds all edges and conditional edges, compiles and returns. Called once at app startup. |
| ⬜ | `get_compiled_graph()` | none | `CompiledGraph` | Cached singleton. Returns compiled graph for use in query service. |

---

### `src/llm/provider.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**Functions:**

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `get_llm()` | `agent_name: str`, `mode: str` | `BaseLLM` | Returns correct LLM instance for given agent and mode. Applies fallback chain: Ollama → Groq → OpenRouter → Gemini → Claude. Logs provider used to Prometheus. |
| ⬜ | `call_llm()` | `llm: BaseLLM`, `prompt: str` | `str` | Wraps LLM call in try/except. On failure, tries next provider in fallback chain. Returns response string. |

---

### `src/llm/prompts.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**What it does:** All prompt templates as string constants. One template per agent task. Never write prompts inside agent files — always import from here.

| Status | Constant | Used By |
| :---- | :---- | :---- |
| ⬜ | `DOMAIN_CLASSIFY_PROMPT` | domain\_classifier.py |
| ⬜ | `QUERY_ANALYZE_PROMPT` | query\_analyzer.py |
| ⬜ | `SEARCH_STRATEGY_PROMPT` | search\_strategy.py |
| ⬜ | `QUERY_REFORMULATE_PROMPT` | retriever.py |
| ⬜ | `EXTRACT_FINDINGS_PROMPT` | reasoner.py |
| ⬜ | `CONTRADICTION_DETECT_PROMPT` | reasoner.py |
| ⬜ | `CITATION_GRAPH_PROMPT` | reasoner.py |
| ⬜ | `SYNTHESIS_PROMPT` | synthesis.py |
| ⬜ | `SYNTHESIS_REFINE_PROMPT` | synthesis.py (when feedback present) |
| ⬜ | `HALLUCINATION_CHECK_PROMPT` | evaluator.py |
| ⬜ | `COMPLETENESS_CHECK_PROMPT` | evaluator.py |

---

## 🗂️ WEEK 3 — PARALLEL AGENTS \+ EVALUATION

### `src/monitoring/metrics.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

**What it does:** Defines all Prometheus Counter, Histogram, and Gauge objects. Every agent imports from here to log metrics. Never create metric objects inside agent files.

| Status | Metric Name | Type | Labels | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `agent_execution_seconds` | Histogram | `agent_name` | Time each agent takes to run |
| ⬜ | `query_type_total` | Counter | `type` | single\_hop vs multi\_hop count |
| ⬜ | `reformulation_total` | Counter | none | How many times query was reformulated |
| ⬜ | `arxiv_fetch_total` | Counter | `domain` | Fresh arXiv fetches per domain |
| ⬜ | `ragas_faithfulness` | Histogram | none | Faithfulness scores distribution |
| ⬜ | `ragas_citation_accuracy` | Histogram | none | Citation accuracy distribution |
| ⬜ | `ragas_quality_score` | Histogram | none | Overall quality score distribution |
| ⬜ | `hallucination_total` | Counter | none | Times hallucination was detected |
| ⬜ | `refinement_loop_total` | Counter | none | Times answer was sent back to Synthesis |
| ⬜ | `llm_provider_calls_total` | Counter | `provider`, `agent` | LLM provider usage per agent |
| ⬜ | `paper_upload_total` | Counter | `visibility` | Paper uploads by visibility |
| ⬜ | `collaboration_created_total` | Counter | `type` | direct\_invite vs project |

---

## 🗂️ WEEK 4 — USER FEATURES

### `src/papers/`

#### `src/papers/models.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Model | Table | Fields | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `Paper` | `papers` | `id (UUID PK)`, `user_id (FK → users)`, `title`, `authors`, `domain`, `source`, `visibility`, `chroma_ids (array)`, `file_path (S3 key)`, `upload_date`, `citation_count` | Metadata record for every paper. `chroma_ids` lists all Chroma chunk IDs so paper can be deleted from Chroma if needed. |

---

#### `src/papers/schemas.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Schema | Fields | Used For |
| :---- | :---- | :---- | :---- |
| ⬜ | `PaperUploadRequest` | `domain`, `visibility`, `title (optional)` | POST /papers/upload form data |
| ⬜ | `PaperOut` | `id`, `title`, `domain`, `visibility`, `source`, `upload_date`, `citation_count` | Response schema |
| ⬜ | `PaperVisibilityUpdate` | `visibility` | PATCH /papers/{id}/visibility |

---

#### `src/papers/service.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `upload_paper()` | `file: UploadFile`, `metadata: PaperUploadRequest`, `user_id: str`, `db: AsyncSession` | `dict` | Saves PDF to S3. Creates Paper record in PostgreSQL. Triggers `ingest_user_paper()` as background task. Returns `{paper_id, status: "processing"}`. |
| ⬜ | `get_user_papers()` | `user_id: str`, `db: AsyncSession` | `list[PaperOut]` | Returns all papers owned by user. |
| ⬜ | `update_visibility()` | `paper_id: str`, `visibility: str`, `user_id: str`, `db: AsyncSession` | `PaperOut` | Changes visibility of paper. If setting to public: also updates Chroma metadata. Private → public is irreversible — raises error if user tries to reverse. |
| ⬜ | `delete_paper()` | `paper_id: str`, `user_id: str`, `db: AsyncSession` | `dict` | Deletes paper from PostgreSQL \+ Chroma (using stored chroma\_ids) \+ S3. Raises 403 if not owner. Raises 400 if paper is public (immutable). |

---

#### `src/papers/router.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Method | Path | Auth | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | POST | `/papers/upload` | JWT | Upload PDF. Form data: file \+ `PaperUploadRequest`. Returns `{paper_id, status}`. Processing happens async in background. |
| ⬜ | GET | `/papers/my-papers` | JWT | List all papers owned by current user. |
| ⬜ | PATCH | `/papers/{id}/visibility` | JWT | Change paper visibility. Body: `PaperVisibilityUpdate`. |
| ⬜ | DELETE | `/papers/{id}` | JWT | Delete paper (owner only, not if public). |
| ⬜ | GET | `/papers/status/{paper_id}` | JWT | Check if async upload processing is complete. Returns `{status: processing/ready/failed}`. |

---

### `src/collaboration/`

#### `src/collaboration/models.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Model | Table | Fields | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `Collaboration` | `collaborations` | `id (UUID PK)`, `type (direct_invite/project)`, `creator_id (FK → users)`, `status (active/archived)`, `project_name`, `description`, `domains (array)`, `open_roles (array)`, `created_at` | Main collaboration record. |
| ⬜ | `CollaborationMember` | `collaboration_members` | `id (UUID PK)`, `collaboration_id (FK)`, `user_id (FK → users)`, `joined_at` | Many-to-many: collaborations → users. |
| ⬜ | `CollaborationPaper` | `collaboration_papers` | `id (UUID PK)`, `collaboration_id (FK)`, `paper_id (FK → papers)`, `added_by (FK → users)`, `added_at` | Papers linked to a collaboration. |
| ⬜ | `CollaborationApplication` | `collaboration_applications` | `id (UUID PK)`, `collaboration_id (FK)`, `user_id (FK → users)`, `status (pending/approved/rejected)`, `interest_note`, `applied_at` | Applications for project-type collaborations. |

---

#### `src/collaboration/service.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Name | Params | Returns | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | `create_direct_invite()` | `creator_id: str`, `paper_id: str`, `db: AsyncSession` | `dict` | Creates Collaboration (type=direct\_invite), links paper, generates invite token. Returns `{collaboration_id, invite_link}`. |
| ⬜ | `accept_invite()` | `invite_token: str`, `user_id: str`, `db: AsyncSession` | `dict` | Validates token, creates pending application, notifies creator. Returns `{status: pending}`. |
| ⬜ | `approve_member()` | `collaboration_id: str`, `applicant_id: str`, `approver_id: str`, `db: AsyncSession` | `dict` | Creator approves member. Adds to CollaborationMember. Updates paper visibility to collaborative in Chroma. |
| ⬜ | `create_project_ad()` | `creator_id: str`, `data: ProjectAdRequest`, `db: AsyncSession` | `dict` | Creates Collaboration (type=project) with ad details. Returns collaboration record. |
| ⬜ | `apply_to_project()` | `collaboration_id: str`, `user_id: str`, `interest_note: str`, `db: AsyncSession` | `dict` | Creates CollaborationApplication (status=pending). Notifies project creator. |
| ⬜ | `get_user_collaborations()` | `user_id: str`, `db: AsyncSession` | `list` | Returns all collaborations user is a member of. |
| ⬜ | `get_open_projects()` | `domain: str | None`, `db: AsyncSession` | `list` | Returns all public project ads. Optional domain filter. |

---

### `src/query/`

#### `src/query/router.py`

| Status | Item |
| :---- | :---- |
| ⬜ | **File created** |

| Status | Method | Path | Auth | Description |
| :---- | :---- | :---- | :---- | :---- |
| ⬜ | POST | `/query` | JWT | Submit query. Body: `{query, llm_mode, domain_hint (optional)}`. Returns full response: answer \+ sources \+ reasoning\_trace. |
| ⬜ | POST | `/query/{query_id}/evaluate` | JWT | On-demand RAGAS evaluation. Returns full RAGAS scores for a previous query. |
| ⬜ | GET | `/query/history` | JWT | Returns user's past queries and answers (paginated). |

---

## 🧪 TESTS

| Status | File | What It Tests |
| :---- | :---- | :---- |
| ⬜ | `tests/test_auth.py` | Register, login, token validation, invalid credentials |
| ⬜ | `tests/test_ingestion.py` | arXiv fetch, PDF extraction, chunking, embedding, Chroma storage |
| ⬜ | `tests/test_search.py` | Semantic search, metadata filters, access control (private papers not visible to others) |
| ⬜ | `tests/test_agents.py` | Each agent node with mock state, full graph run with sample query |
| ⬜ | `tests/test_collaboration.py` | Invite flow, project ad \+ application flow, permission checks |
| ⬜ | `tests/test_papers.py` | Upload, visibility change, delete, S3 interaction |

---

## 🐳 DEPLOYMENT

| Status | Task |
| :---- | :---- |
| ⬜ | `Dockerfile` — multi-stage build for FastAPI app |
| ⬜ | `docker-compose.yml` — FastAPI \+ PostgreSQL \+ Chroma \+ Prometheus \+ Grafana \+ MinIO |
| ⬜ | `.env.example` — all required env vars documented |
| ⬜ | AWS EC2 instance setup (Ubuntu 24, t3.large) |
| ⬜ | Ollama installed on EC2 with models pulled |
| ⬜ | PostgreSQL RDS or EC2 PostgreSQL setup |
| ⬜ | S3 bucket created with correct IAM permissions |
| ⬜ | GitHub Actions CI/CD pipeline (test → build → deploy) |
| ⬜ | Domain \+ SSL (Nginx reverse proxy \+ Certbot) |
| ⬜ | Grafana dashboard imported and connected to Prometheus |

---

## 📝 SESSION LOG

Add a row after every working session.

| Date | Session \# | What was done | Files created/modified | Next task |
| :---- | :---- | :---- | :---- | :---- |
| 2026-07-07 | 1 | Set up host DB proxy for Supabase, fixed Chroma list metadata validation crash, implemented paper duplication skip checks for ingestion resumption, configured unbuffered logs, added custom HTTP requests metrics middleware in FastAPI, force-recreated Prometheus container with correct scrape trailing slash, added custom keyword query filtering for new GenAI domain. | `src/ingestion/pipeline.py`, `src/ingestion/arxiv_fetcher.py`, `src/main.py`, `docker/prometheus.yml`, `scripts/inspect_chroma.py`, `scripts/local_db_proxy.py` | Complete remaining domains ingestion & monitor health. |

---

## 🔖 NOTES & DECISIONS

Track important decisions made during development.

| Date | Decision | Reason |
| :---- | :---- | :---- |
| — | Single Chroma DB with metadata filters (not per-user DB) | Cost constraint, 225k docs is well within single instance limits |
| — | Binary permissions only (private/public) in MVP | Simpler to build, granular permissions in v2 |
| — | RAGAS on-demand only (not every query) | Cost and latency — Prometheus handles internal monitoring |
| — | arXiv fresh fetch instead of web search | Controlled quality, papers stay in Chroma for future use |
| — | Async paper upload processing | UX — user doesn't wait 2 minutes for upload to complete |
| — | All prompts in `src/llm/prompts.py` | Single place to tune prompts without touching agent logic |

