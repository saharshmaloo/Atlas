# Atlas

**Research that compounds.**

Atlas is an open-source, agentic research workspace that investigates complex questions, organizes sources, and builds a persistent, evidence-backed knowledge base across research sessions.

Unlike a conventional research chatbot that produces an answer and forgets its supporting work, Atlas is designed to preserve **sources, claims, relationships, and open questions**. Each investigation can reuse and challenge prior findings without treating generated text as ground truth.

> **Status:** Early development. The backend provides persistent workspaces and UTF-8 text source uploads, listing, and retrieval. The research features below describe the intended architecture and roadmap.

## Local Development

Requires Python 3.12 or newer. From the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn atlas.main:app --reload
```

Visit <http://127.0.0.1:8000/docs> for interactive API documentation, or check liveness:

```sh
curl --fail http://127.0.0.1:8000/health
# {"status":"ok"}
```

`GET /health` checks that the API process responds; it does not check database or model-provider readiness. Health checks run without a database. Workspace endpoints require PostgreSQL; no model API keys are needed.

### Workspaces and PostgreSQL

With Docker Compose installed, start the local database and apply migrations from the activated Python environment:

```sh
docker compose up -d --wait db
cp .env.example .env
set -a
source .env
set +a
python -m alembic upgrade head
python -m uvicorn atlas.main:app --reload
```

The application and migrations read `DATABASE_URL` from the process environment; `.env` is loaded explicitly above. The default URL matches the local Compose database. Compose credentials are for local development. Database files persist in a named volume across container restarts. Schema migrations run explicitly, not on API startup.

Create a workspace, then retrieve it using the returned UUID:

```sh
curl --fail http://127.0.0.1:8000/workspaces \
  -H 'Content-Type: application/json' -d '{"name":"Distributed Databases"}'
curl --fail 'http://127.0.0.1:8000/workspaces/<returned-id>'
```

Creation returns HTTP 201 with `id`, `name`, and a timezone-aware `created_at`. Names are trimmed and must contain 1–200 characters. Invalid input returns 422; an unknown UUID returns 404. Names need not be unique.

### Text Sources

Apply the latest migration with `python -m alembic upgrade head`, then upload a UTF-8 `.txt` file into an existing workspace:

```sh
curl --fail 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources' \
  -F 'file=@notes.txt'
curl --fail 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources?limit=50&offset=0'
curl --fail 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources/<source-id>'
curl --fail 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources/<source-id>/content'
```

Uploads return HTTP 201 with `id`, `workspace_id`, `title`, `content_hash` (SHA-256 of the uploaded bytes), and `created_at`. The title is the filename with directory components removed, capped at 200 characters. Original UTF-8 contents, including BOM, line endings, and spacing, are preserved exactly in PostgreSQL and returned as `text/plain; charset=utf-8` by `/content`.

Files are limited to 1 MiB; multipart requests are capped at 1 MiB + 64 KiB before parsing. Oversized uploads return 413. Unsupported extensions, invalid UTF-8, empty/whitespace-only files, and NUL characters return 422. Metadata lists contain no document contents and use `limit` (1–100, default 50) and `offset` (default 0). Unknown workspaces return 404; source retrieval returns 404 when a source is missing or belongs to a different workspace. Duplicate uploads are retained as separate sources with matching hashes. Workspace scoping is not user authentication.

### Source Passages

Apply the latest migration with `python -m alembic upgrade head`. Passage generation is explicit:

```sh
curl --fail -X POST 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources/<source-id>/passages'
curl --fail 'http://127.0.0.1:8000/workspaces/<workspace-id>/sources/<source-id>/passages?limit=50&offset=0'
```

Generation returns HTTP 200 with `source_id` and `passage_count`. Repeated or concurrent requests reuse existing passages. Listing returns an empty array before generation and ordered passages afterward; `limit` is 1–100 (default 50) and `offset` defaults to 0. Missing sources and sources outside the requested workspace return 404.

Each passage records `id`, `source_id`, zero-based `position`, `start_char`, `end_char`, `text`, and `chunker_version`. Offsets count Unicode code points (Python string indexes), with an exclusive end; `source[start_char:end_char]` equals `text`. They are not UTF-8 byte or JavaScript UTF-16 offsets. Joining all passages in position order reproduces the original source exactly.

The fixed `paragraph-v1` algorithm produces non-overlapping spans of at most 1,000 characters, preferring the last blank-line boundary within the limit (LF or CRLF, with optional spaces/tabs on the blank line). Long paragraphs split at the character limit. Whitespace, BOM, and line endings are preserved. Passage UUIDs derive from the source ID, chunker version, and offsets, so retries keep IDs stable. Future chunker changes must use a new version and an explicit regeneration strategy; this endpoint does not replace existing passages.

### Keyword Search

Apply the latest migration with `python -m alembic upgrade head`. After uploading sources and generating passages, search within a workspace:

```sh
curl --fail --get 'http://127.0.0.1:8000/workspaces/<workspace-id>/search' \
  --data-urlencode 'q=distributed transactions' --data-urlencode 'limit=10'
```

Search returns HTTP 200 with ranked passage records plus `source_title` and `score`. Each result includes the stable passage `id`, `source_id`, `position`, `start_char`, `end_char`, exact `text`, and `chunker_version` needed to trace it to the original source. Results are ordered by descending relevance, with source ID and passage position breaking ties consistently.

Queries use PostgreSQL English full-text search: words are case-insensitive and stemmed, common stop words are ignored, and ordinary terms must all match within one passage. Quoted phrases, `OR`, and `-excluded` terms are supported. Search covers passage text, not source titles or sources without generated passages. It is keyword retrieval, so synonyms and meaning alone do not produce matches.

`q` is required, limited to 500 characters, and must contain non-whitespace text without NUL characters. `limit` is 1–50 (default 10). Invalid parameters return 422, unknown workspaces return 404, and searches without matches return an empty array (including stop-word-only and punctuation-only queries). Relevance scores are relative ranking values, not confidence or factuality scores.

A stored generated search vector and GIN index cover existing passages during migration and update automatically for new passage text. No external search service or API key is needed.

### Tests

Run the tests from the same activated environment:

```sh
python -m pytest -q
```

Tests cover the health response, unsupported HTTP methods, unknown routes, and starting the installed application with Uvicorn over a real local HTTP connection. The server test requires permission to bind a loopback socket and uses POSIX socket inheritance (macOS/Linux).

Run the complete suite against a separate PostgreSQL test service:

```sh
docker compose --profile test up -d --wait test-db
export TEST_DATABASE_URL=postgresql+psycopg://atlas:atlas@127.0.0.1:5433/atlas_test
python -m pytest -q
```

Database tests skip explicitly when `TEST_DATABASE_URL` is unset. When it is set, an unavailable database fails the tests. The test role needs `CREATEDB`; each test migrates a uniquely named temporary database and drops only that database afterward. Tests verify migration upgrades and downgrades, schema/model agreement, persisted workspaces across application restarts, name validation, distinct IDs, and missing workspace responses.

## Why Atlas?

Research is cumulative, but most AI research workflows are ephemeral. Users repeatedly find the same sources, reconstruct prior context, and struggle to audit where conclusions came from.

Atlas aims to make research:

- **Persistent:** Findings and evidence remain available across sessions.
- **Grounded:** Claims link to identifiable passages in versioned sources.
- **Agentic:** Complex questions are decomposed into parallel, inspectable tasks.
- **Revisable:** New evidence can challenge, supersede, or strengthen previous conclusions.
- **Observable:** Users can see what the agent searched, retrieved, inferred, and verified.

## Example Workflow

Create a workspace called **Distributed Databases** and ask:

> Compare how Spanner, CockroachDB, and TiDB handle distributed transactions. Focus on concurrency control and failure recovery.

Atlas would:

1. Break the question into focused research tasks.
2. Discover and ingest relevant papers, documentation, and engineering articles.
3. Retrieve relevant passages through hybrid search and reranking.
4. Synthesize a comparison with passage-level citations.
5. Check that cited evidence supports the report's important claims.
6. Save sources, claims, relationships, and unanswered questions to the workspace.

Later, ask:

> How does FoundationDB compare with the systems we researched last week?

Atlas can reuse prior evidence, identify what needs fresh research, and update the workspace rather than starting over.

## Planned Features

### Research Agent

- Natural-language research requests and follow-up questions
- Search and document-reading tools
- Task planning and parallel subtask execution
- Streaming progress and inspectable tool traces
- Source-linked reports and comparisons

### Retrieval-Augmented Generation

- Webpage and PDF ingestion
- Structure-aware chunking with document location metadata
- Hybrid dense-vector and keyword retrieval
- Reranking and contextual query rewriting
- Source deduplication and version tracking

### Persistent Knowledge

- Workspaces with source libraries and research history
- Claims linked to supporting or conflicting evidence
- Reuse of verified findings in later research
- Research questions, gaps, and revisions over time
- Explicit separation of source evidence from model-generated interpretation

### Reliability and Evaluation

- Durable, resumable research runs
- Retries, timeouts, cancellation, and execution budgets
- Claim-to-citation verification
- Retrieval and answer-quality evaluation suites
- Latency, token usage, cost, and tool-call observability

## Architecture

```mermaid
flowchart TD
    UI[Web Client] --> API[API Service]
    API --> ORCH[Research Orchestrator]
    ORCH --> PLAN[Planner]
    PLAN --> SEARCH[Search & Ingestion Tools]
    PLAN --> RETRIEVE[Retrieval Service]
    SEARCH --> DOCS[(Source Store)]
    DOCS --> INDEX[(Search Indexes)]
    INDEX --> RETRIEVE
    RETRIEVE --> SYNTH[Synthesis & Verification]
    SEARCH --> SYNTH
    SYNTH --> CLAIMS[(Claims & Evidence Store)]
    SYNTH --> API
    CLAIMS --> RETRIEVE
```

### Core Components

| Component | Responsibility |
| --- | --- |
| API service | Workspaces, conversations, research runs, streaming updates |
| Research orchestrator | Task state, scheduling, concurrency, retries, cancellation |
| Planner | Break broad questions into actionable investigations |
| Ingestion workers | Fetch, parse, chunk, deduplicate, and version documents |
| Retrieval service | Hybrid search, reranking, and provenance-preserving context assembly |
| Synthesis and verification | Write reports and evaluate claim-to-evidence support |
| Knowledge store | Persist sources, claims, relationships, and research history |

## Evidence-First Memory

The core design principle is that **a claim is not a source**.

Atlas stores original source passages separately from the model's interpretations. A research claim records its evidence links and verification state so future runs can inspect or challenge it.

Illustrative entities:

```text
Workspace
  id, name, created_at

Source
  id, uri, title, content_hash, retrieved_at, version

Passage
  id, source_id, text, location, embedding

Claim
  id, workspace_id, statement, verification_status, created_at

ClaimEvidence
  claim_id, passage_id, relationship  # supports | contradicts | mentions

ResearchRun
  id, workspace_id, question, status, started_at, completed_at

ResearchTask
  id, run_id, parent_task_id, objective, status, attempts
```

The system should never silently promote an unverified model conclusion into authoritative knowledge. Contradictory evidence should remain visible rather than being overwritten.

## Agent Execution Model

A research run is represented as a dynamically evolving task graph:

1. **Plan:** The LLM proposes research subtasks and tool calls.
2. **Execute:** Independent tasks run concurrently within configured budgets.
3. **Collect:** Results and source references are stored durably.
4. **Evaluate:** The agent identifies missing evidence or unresolved conflicts.
5. **Iterate:** Follow-up tasks are created when useful and within budget.
6. **Synthesize:** A report is generated and citation support is checked.
7. **Persist:** Research artifacts are committed to the workspace's knowledge base.

State transitions and external tool effects should be designed for **at-least-once execution**: a retry must not accidentally duplicate an ingested document or corrupt a research run. This motivates idempotency keys, durable checkpoints, and explicit task states.

## Proposed Tech Stack

| Layer | Candidate technology |
| --- | --- |
| Frontend | React / Next.js |
| Agent and ingestion services | Python |
| API | Python/FastAPI initially; Go as a possible later service boundary |
| Relational data | PostgreSQL |
| Dense retrieval | pgvector |
| Keyword retrieval | PostgreSQL full-text search |
| Background execution | Worker queue initially; Temporal as a durable-workflow option |
| Source content | S3-compatible object storage |
| Telemetry | OpenTelemetry |
| Models | Provider-agnostic LLM and embedding adapters |

These are design candidates, not installed dependencies. The initial implementation should favor a small number of services and clear interfaces over premature microservice decomposition.

## Roadmap

### Phase 1 — End-to-End Research MVP

- [ ] Create and manage research workspaces
- [ ] Ingest webpages and PDFs
- [ ] Chunk, embed, and index sources
- [ ] Implement hybrid retrieval
- [ ] Generate answers with passage-level citations
- [ ] Provide a minimal chat and sources UI

### Phase 2 — Agentic Research

- [ ] Plan multi-step investigations
- [ ] Execute independent tool calls concurrently
- [ ] Stream task progress to the UI
- [ ] Record tool inputs, outputs, failures, and latency
- [ ] Add timeout, retry, cancellation, and budget controls

### Phase 3 — Compounding Knowledge

- [ ] Extract atomic claims from research outputs
- [ ] Link claims to supporting and conflicting passages
- [ ] Reuse prior claims and evidence across sessions
- [ ] Deduplicate sources and detect changed content
- [ ] Surface unresolved questions and conflicting evidence

### Phase 4 — Reliability and Quality

- [ ] Make long-running research tasks durable and resumable
- [ ] Implement claim-level citation verification
- [ ] Build a labeled retrieval and citation benchmark
- [ ] Instrument traces, latency, token usage, and cost
- [ ] Compare research quality with and without persistent memory

## Evaluation

Atlas should be evaluated as a research system, not only as a fluent text generator.

| Dimension | Example metric |
| --- | --- |
| Retrieval | Recall@k, MRR, nDCG on labeled source passages |
| Grounding | Percentage of factual claims supported by cited passages |
| Citation quality | Citation precision and missing-citation rate |
| Memory utility | Quality improvement on follow-up tasks using prior research |
| Reliability | Research-run completion and recovery rates |
| Performance | End-to-end latency, tool latency, cost per completed run |

The most important experiment is an **ablation of persistent research memory**: use the same questions and model configuration with and without prior evidence-backed claims, then compare grounded answer quality, repeated retrieval work, and cost.

## Non-Goals (Initially)

- Building a general-purpose search engine or foundation model
- Supporting every document type and third-party connector
- Fully autonomous research without user-scoped budgets
- Treating confidence scores as proof of factual correctness
- Building a complex knowledge graph before simpler relational memory proves useful
- Replacing source reading with opaque, unverifiable summaries

## Security and Responsible Use

- Treat retrieved webpages and documents as untrusted input; they must not override agent instructions or authorize tool actions.
- Restrict tool permissions and sandbox executable operations.
- Respect source access controls and licensing requirements.
- Avoid storing secrets in prompts, traces, or research reports.
- Separate workspace data by ownership and enforce authorization at retrieval time.
- Present uncertainty and evidence conflicts rather than fabricating certainty.

## Project Goals

Atlas is also a hands-on exploration of three engineering areas:

1. **Agentic infrastructure:** Long-running orchestration, stateful tool execution, concurrency, and failure recovery.
2. **Applied retrieval:** Ingestion, chunking, indexing, ranking, grounding, and evaluation.
3. **AI product engineering:** Turning agent capabilities into a useful, inspectable, persistent research workflow.

## License

License to be determined before public release.
