# Atlas local research operations

Milestones 1–4 are implemented for a local, single-user prototype. Start PostgreSQL, install `.[dev,browser]`, load `.env` into the process environment, run `python -m alembic upgrade head`, and start `python -m uvicorn atlas.main:app --reload`. Open <http://127.0.0.1:8000/>. Apply migrations before using the expanded API.

## Providers and configuration

No provider is required to upload sources, generate passages, run keyword search, or reopen history. Real providers are called only by explicit submissions or explicitly started research workers. Tests clear inherited live provider configuration and inject fakes/mocked HTTP.

| Environment variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Server-side credential for configured OpenAI adapters |
| `OPENAI_MODEL` | Answer model supporting Responses Structured Outputs |
| `ATLAS_VERIFIER_MODEL` | Optional separate Structured Outputs model for semantic judgments |
| `ATLAS_EMBEDDING_MODEL` | Optional embedding model supporting the `dimensions` parameter |
| `ATLAS_EMBEDDING_DIMENSIONS` | Vector dimensions, default 1536; supported range 1–4096 |
| `ATLAS_EMBEDDING_VERSION` | Explicit embedding profile version, default `1` |
| `ATLAS_RERANKER` | Set `lexical-v1` to enable the optional term-overlap reranker |

The embedding adapter follows the [official OpenAI documentation](https://developers.openai.com/api/reference/resources/embeddings/methods/create). Set a model/dimension combination supported by your account; model access and real model quality are not covered by fake-provider tests. Embeddings are generated only through explicit requests, not automatically on upload. Changing provider/model/dimensions/version creates a separate immutable profile.

Without a semantic verifier, every claim judgment remains explicitly **uncertain**. With one configured, `supported`, `unsupported` (contradicted), and `uncertain` are fallible assessments, not proof. Verifier responses must cover each claim exactly once and reference only its saved citations. Claims and original answer snapshots remain unchanged when judgments are added. Answer/verifier adapters set `store=false`, bound outputs, use a 30-second SDK timeout, and disable automatic retries.

## Sources, originals, and versions

Use the workspace upload form for UTF-8 `.txt` or text-based `.pdf` files, or save a public webpage URL. Inspect the original/extracted text, generate passages, then search or ask a question. All uploads/fetched bodies are capped at 1 MiB.

| Operation | API |
| --- | --- |
| Upload text | `POST /workspaces/{w}/sources`, multipart `file` |
| Upload PDF | `POST /workspaces/{w}/sources/pdf`, multipart `file` |
| Save webpage | `POST /workspaces/{w}/sources/web`, JSON `{"url":"https://example.org/article"}` |
| Download retained original | `GET /workspaces/{w}/sources/{s}/original` |
| Add text version | `POST /workspaces/{w}/sources/{s}/versions`, multipart `file` |
| Add PDF version | `POST /workspaces/{w}/sources/pdf?previous_source_id={s}`, multipart `file` |
| Refresh webpage version | `POST /workspaces/{w}/sources/web`, JSON `{"url":"https://example.org/article","previous_source_id":"{s}"}` |
| Browse versions | `GET /workspaces/{w}/sources/{s}/versions?offset=0`, 50 per page |
| Detect duplicates | `GET /workspaces/{w}/sources/{s}/duplicates?offset=0`, 50 per page |

The source view offers matching replacement/refresh controls and version navigation. New versions get new source/passage IDs while retaining a document ID and increasing version number. Earlier content and citations remain available. Duplicate uploads and equal-content versions remain distinct; duplicate detection never crosses workspaces.

Text uploads retain original UTF-8 bytes including line endings/BOM. PDFs retain original bytes and extracted page spans (at most 200 pages), with a timed CPU-bounded extraction worker and a 512 MiB address-space cap on Linux. Encrypted, malformed, oversized, and image-only PDFs are rejected; OCR is not implemented. PDF/page offsets refer to extracted Unicode text, never PDF byte positions. Extraction is not a faithful representation of arbitrary PDF layouts.

Web ingestion accepts public HTTP(S), ports 80/443, and UTF-8 uncompressed HTML/plain text. All DNS answers and redirect targets must be public; connections use validated pinned addresses while TLS verifies the original hostname. Private, loopback, link-local, multicast, credential-bearing, and unsupported URLs are rejected. Fetches have a hard worker deadline, at most three redirects, and bounded streaming reads. JavaScript is not executed. Active HTML content is excluded from extracted text; original bytes, final URL, retrieval time, and extractor version are retained.

## Retrieval, answers, and verification

Keyword retrieval remains the default. The browser's **Generate embeddings** button processes at most 16 pending passages per click; prior completed batches survive failures. The API supports `POST /workspaces/{w}/embeddings?batch_size=16&max_batches=1`, with at most four batches/request. Responses include profile ID, counts, remaining work, and completion state. `GET /workspaces/{w}/embeddings/{profile_id}` reads status without provider credentials.

Vectors are finite, normalized, and immutable per passage/profile. This prototype stores vectors in PostgreSQL JSONB and uses exact cosine ranking over **at most 1,000 embedded workspace passages**. It rejects larger exact searches rather than silently truncating. An ANN index/service is future scaling work.

- `GET /workspaces/{w}/vector-search?q=...&limit=10` returns profile-matched nearest passages.
- `GET /workspaces/{w}/hybrid-search?q=...&limit=10` fuses up to 50 keyword/vector candidates each using reciprocal rank fusion (constant 60), deduplicating stable passage IDs. Vector candidates below cosine 0.2 are excluded. Provider/configuration/size failures fall back explicitly to keyword results.
- Add `rerank=true` to hybrid search or an answer request to use a configured optional reranker. Invalid, duplicate, missing, or failed rankings preserve original order. The lexical baseline is term overlap, not semantic verification.
- `POST /workspaces/{w}/answers` accepts `question`, optional `retrieval: "keyword" | "hybrid"`, `rerank` (default false), and `use_memory` (default false). The browser offers retrieval selection and opt-in memory expansion.

Answer snapshots record provider/model identity, prompt/retrieval versions, retrieval limits, reranking outcome, reused-memory passage count, and generation duration. Older records without provenance remain readable.

Use `Idempotency-Key` (1–128 characters) on answer submissions to reuse the same saved result after retries. Keys are scoped to workspace and normalized request content; conflicting content returns 409. Concurrent retries serialize before any answer provider call. Failed requests can retry their keys. Successful submissions without a key remain separate history records.

`POST /workspaces/{w}/answers/{a}/verifications` appends a separate assessment; GET lists the latest 20 assessments. Optional `Idempotency-Key` makes a verification effect retry-safe. The browser's **Check claim support** control opens these assessments on saved answers; citation controls always inspect the original saved evidence snapshot.

## Durable research runs

Create a run from the workspace UI or `POST /workspaces/{w}/runs` with `{"objective":"How do transactions work?"}`. Creation persists one queued answer task and starts no background work. Set `use_memory: true` (or check **Use supported research memory** in the browser) to persist opt-in evidence expansion for every answer task in that run. It defaults to false. Optional `budgets` override validated defaults:

| Budget | Default | Bounds |
| --- | --- | --- |
| Attempts per task | 3 | 1–5 |
| Concurrent leased tasks | 1 | 1–4 |
| Reserved model calls | 3 | 0–100 |
| Tool attempts | 8 | 0–100 |
| Wall-clock seconds from first claim | 300 | 1–3600 |
| Reserved model tokens | 500,000 | 0–10,000,000 |

Budget JSON keys are `max_attempts`, `max_concurrency`, `max_model_calls`, `max_tool_calls`, `max_seconds`, and `max_model_tokens`. Model reservations conservatively charge an answer attempt 52,000 input/output token units and verification 196,000, including retries/cached effects or unconfigured verification; they are upper-bound reservations, not billing measurements. No model task starts with less than 31 seconds remaining. Budgets stop further work; cancellation cannot undo an already-started provider request or an already-saved answer. Exhausted runs require a new explicitly budgeted run rather than silently replenishing limits.

**Plan saved-evidence steps** calls `POST /runs/{r}/plan` on an unstarted run. The default deterministic planner creates search → answer → verify. Plans are limited to eight tasks, validated as ordered acyclic dependencies, and constrained to those saved-evidence tools and the run's budgets. Retrieved instructions cannot authorize shell commands or arbitrary tools. Planning does not perform autonomous webpage discovery.

Execute tasks with **Run next task**, `POST /workspaces/{w}/runs/{r}/step`, or an explicit worker:

```sh
python -m atlas.worker          # process at most one ready task
python -m atlas.worker --watch  # poll durable tasks every two seconds
```

Workers serialize claims, issue 120-second leases/fencing tokens, recover expired leases, and reject stale checkpoints. Answer and verification effects use stable task request keys, so a lost checkpoint does not repeat a completed model effect. Verification also remembers the answer's fallible claims/evidence. Failed tasks retry only within their remaining budgets.

`POST /runs/{r}/cancel` fences unfinished tasks. `POST /runs/{r}/resume` requeues eligible work while retaining completed tasks, attempts, reservations, and the original deadline. Completed runs cannot be cancelled; exhausted attempts/time cannot be reset by resuming.

Run URLs use `/#/workspaces/{w}/runs/{r}`. Lists/details survive restarts. `GET /runs/{r}/events?after=0&limit=50` returns ordered operational events. `GET /runs/{r}/events/stream` streams SSE with `Last-Event-ID`/`after` replay, heartbeats, and terminal closure. The browser reconnects from its last sequence, including after resume. Events contain statuses, durations, counts, and sanitized error categories; prompts/source text/provider payloads and secrets are excluded.

## Research memory and unresolved questions

**Save claims to memory** or `POST /workspaces/{w}/answers/{a}/remember` retains atomic generated interpretations and their original citation snapshots. It reuses stable IDs on retries and appends changed assessments instead of overwriting evidence. Optional `verification_id` selects an assessment belonging to that answer. `GET /claims`, `GET /claims/{id}`, and `GET /memory-search?q=...` expose workspace-scoped findings separately from original sources.

Memory expansion supplies only original passages with a current source version and a supported assessment matching the **latest** saved verification. It excludes uncertain, unsupported, contested, superseded, missing-source, changed-text, and outdated-assessment findings. Generated claim text is never substituted for original evidence. New judgments immediately invalidate older supported memory until it is assessed/materialized consistently. Historical snapshots remain inspectable.

`POST /claim-relations` records explicit `contradicts` or `supersedes` links with `from_claim_id`, `to_claim_id`, and a `note`. Supersession cycles/self-links/foreign claims are rejected. Disagreements remain unresolved; the system does not overwrite earlier interpretations or infer that a user-created relationship proves a fact.

`POST /questions` saves `{"question":"What remains uncertain?"}`. GET lists questions; `POST /questions/{id}/updates` appends `{"status":"resolved","note":"Evidence reviewed"}` or an `open` update. Original questions and all resolution/reopening notes remain available. The browser supports findings, relationships, evidence inspection, and open-question updates.

## Verification and limits

Run all unit, PostgreSQL, packaging, evaluation, and Chromium checks:

```sh
docker compose --profile test up -d --wait test-db
python -m playwright install chromium
STRICT_TESTS=1 RUN_BROWSER_TESTS=1 TEST_DATABASE_URL=postgresql+psycopg://atlas:atlas@127.0.0.1:5433/atlas_test python -m pytest -q -W error
```

CI installs a built package and runs PostgreSQL/migration tests and a separate packaged-UI/Chromium job. Strict mode fails if any selected test skips. Browser tests use disposable migrated databases and fake providers, covering narrow/desktop workflows, failures, versioning, progress recovery, evidence, and memory. [Evaluation fixtures](../benchmarks/README.md) report retrieval, citation membership, semantic-support labels, abstention, and memory ablations separately. Synthetic fake results are not evidence of live-model quality or general cost/latency improvement.

Keep this prototype local. Multi-user identity/ownership authorization, abuse limits, public deployment configuration, backups/restore, ANN-scale retrieval, arbitrary web-agent tooling, and live-model evaluations remain separate work beyond these milestones.
