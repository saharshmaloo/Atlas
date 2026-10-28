# Atlas implementation plan

## Current status

Milestones **1–4 are complete** for the local prototype. All slices 01–38 have implementations and tests, with larger API/UI features split into independently reviewable commits below 500 added/deleted lines. The operations guide in `docs/OPERATIONS.md` documents configuration, endpoints, workers, bounds, and future hosting work.

Milestone 2 includes PostgreSQL/installed-wheel/browser CI, labeled evaluations, generation provenance, concurrent request idempotency, and separate semantic judgments. Milestone 3 adds immutable source versions/duplicate detection, bounded PDF/public-web ingestion, versioned embeddings, exact vector/hybrid retrieval, and optional reranking. Milestone 4 adds durable leased tasks, persistent budgets, cancellation/resume, bounded saved-evidence planning, replayable progress, claims/evidence relationships, memory retrieval, conflicts/supersession, and open questions.

Full-suite checkpoints passed 136 tests after milestone 2 and 186 after milestone 3. Final milestone 4 verification passed **222 tests with zero skips** using `STRICT_TESTS=1 RUN_BROWSER_TESTS=1` and `-W error`. The local development database is migrated through revision `0019`, and the running app exposes the new routes. Hosted CI is configured; it has not been run on GitHub for these local commits. Tests use Docker PostgreSQL, Chromium at narrow/desktop widths, fake providers/mocked HTTP, and warnings as errors. Live model quality, other browser engines, physical devices, and ANN-scale retrieval remain unverified. Keyword retrieval and opt-in memory defaults are unchanged; default semantic judgments remain uncertain without explicit verifier configuration.

The memory ablation improves fixture coverage from 2/3 to 1.0 with increased provider calls and unchanged keyword retrieval work; it does not demonstrate live-model quality, cost, or latency improvements. See `benchmarks/README.md`.

## Commit rules

- Keep every commit below 500 added/deleted lines across the entire change, including tests and documentation. Aim for 200–400 to leave room for fixes.
- Keep related implementation, meaningful tests, and necessary usage documentation together. If a slice grows too large, split it into independently working steps before committing.
- Use the proposed commit subjects below, with a concise body explaining what changed, why, and how it was verified.
- Run relevant tests against Docker PostgreSQL. Run the full suite before completing a milestone, with warnings treated as errors. Model tests use fakes or mocked HTTP; live model checks are explicitly separate.
- Preserve workspace isolation, exact source text, stable passage IDs, and citation snapshots throughout.
- Sequence numbers express order, not permission to implement or publish the entire roadmap automatically.

## Milestone 1: complete the browser research flow — complete

Continue with the existing FastAPI-served HTML/CSS/JavaScript UI. A framework migration is a separate decision, not a prerequisite.

### 01 — `feat: add workspace browser interface`

- Commit the current workspace UI and workspace-list endpoint as their own change.
- Finish package verification: ensure a built wheel includes all three static assets.
- Check narrow-screen layout and library/detail navigation in Chrome; record any checks that remain unverified.
- Done: a fresh installation serves the UI, and a workspace can be created and reopened after refresh.

### 02 — `feat: upload and browse sources in a workspace`

- Add a sources section inside the workspace view using the existing paginated source-list endpoint.
- Add a `.txt` upload form, upload progress state, and inline validation/server errors.
- Prevent duplicate submission while a request is pending; refresh the source list after success.
- Verify valid upload, invalid UTF-8, empty/oversized files, empty lists, and changing workspaces during a request.
- Done: a document uploaded through the browser remains visible after refresh.

### 03 — `feat: inspect source text and generate passages`

- Add a source detail view with original text rendered as text, preserving spacing and line endings.
- Add explicit passage generation, generation state, and a paginated passage list with positions and offsets.
- Keep source selection in the URL so refresh and browser navigation restore the same document.
- Verify long documents, Unicode, repeated generation, missing sources, and stale requests after navigation.
- Done: a user can inspect the document and its generated passages without using API documentation.

### 04 — `feat: search workspace evidence in the browser`

- Add a keyword-search form and ranked passage results with source titles.
- Support loading, no-results, validation, and failure states; preserve the query when opening a source.
- Link each result to its original source and passage using stable IDs and offsets.
- Verify workspace scoping, repeated queries, keyboard submission, and navigation between results and sources.
- Done: a user can find evidence and inspect where it came from.

### 05 — `feat: ask questions from the workspace interface`

- Add a question form using the existing answer endpoint, with pending state and duplicate-submit prevention.
- Render returned claims and their citation links safely; display insufficient-evidence responses explicitly.
- Present useful messages for missing provider configuration, timeouts, and invalid provider responses.
- Keep provider credentials on the server. Test with a fake provider; do not require paid calls for verification.
- Done: the browser shows a saved answer with links to its supporting passage IDs.

### 06 — `feat: inspect answer citation evidence`

- Make citation links open the saved citation snapshot, including source title, passage text, and original offsets.
- Offer navigation to the current source separately; retain the historical snapshot if source metadata changes.
- Explain that valid citation IDs do not establish semantic support. Keep focus handling and keyboard dismissal usable.
- Verify multiple claims sharing citations, Unicode offsets, missing current sources, and untrusted text rendering.
- Done: every displayed claim's cited evidence can be inspected directly.

### 07 — `feat: browse and reopen saved answer history`

- Add newest-first paginated history using the existing summary endpoint.
- Open full saved answers through their own URLs, reusing answer and citation rendering.
- Restore question, status, timestamp, claims, and evidence without making another model request.
- Verify refresh, back/forward navigation, empty history, insufficient evidence, and missing/foreign answer IDs.
- Done: past research can be reopened after restarting the API, even without provider credentials.

### 08 — `test: automate the browser research workflow`

- Add a small, reproducible browser regression harness with a disposable database and fake provider.
- Cover create workspace → upload → generate passages → search → ask → inspect citation → reopen history.
- Add targeted checks for narrow screens, keyboard operation, error recovery, and HTML-like source/name text.
- Document test installation and execution. If fixture setup and assertions exceed the line budget, split this commit.
- Done: the complete browser flow is repeatable without personal data, real credentials, or paid model calls.

**Milestone exit:** the complete saved-source research workflow is usable in the browser. Search remains keyword-based, and answer support is not yet semantically verified.

## Milestone 2: measurable reliability and answer quality — complete

Each row is a separate proposed commit. Reassess estimates before implementation; split any row that would exceed the line limit.

| Order | Commit subject | Scope and verification |
| --- | --- | --- |
| 09 | `ci: run PostgreSQL integration tests` | Run migrations and the existing suite in CI with a PostgreSQL service, explicit test configuration, and no skipped database tests. |
| 10 | `ci: verify packaged UI and browser workflow` | Install the built package and run the browser smoke workflow in CI; ensure assets work outside the checkout. Depends on 08–09. |
| 11 | `test: add a labeled retrieval benchmark` | Add a small versioned corpus, questions, expected passage references, and a reproducible keyword-retrieval baseline. |
| 12 | `feat: record answer generation provenance` | Save provider/model identity, retrieval configuration, prompt version, and generation duration alongside new answers; preserve older history compatibility. |
| 13 | `feat: make answer submissions idempotent` | Accept request keys scoped to workspace and request content; reuse completed submissions and reject conflicting key reuse. Test concurrent retries and failure behavior. |
| 14 | `feat: classify claim support against cited evidence` | Add a bounded verifier interface and structured supported/unsupported/uncertain judgments with evidence references. Test its contract using fakes; do not call judgments proof. |
| 15 | `feat: persist and display claim verification results` | Store verification separately from original claims and show support state in saved answers. Split storage/API and UI commits if needed. |
| 16 | `test: benchmark answer grounding and abstention` | Add labeled support and insufficient-evidence cases; report citation membership and semantic support as different metrics. Compare with the retrieval baseline. |

**Milestone exit:** failures are reproducible, history has generation provenance, and retrieval/answer changes can be evaluated against labeled examples.

## Milestone 3: broaden retrieval and ingestion — complete

These slices depend on the preceding evaluation baseline. Choose concrete libraries and provider settings when implementing, rather than treating README candidates as installed dependencies.

| Order | Commit subject | Scope and verification |
| --- | --- | --- |
| 17 | `feat: track source provenance and versions` | Add source kind, original location, retrieval timestamp, and explicit immutable versions; preserve old source references and answer snapshots. |
| 18 | `feat: detect duplicate source content` | Define workspace-scoped duplicate behavior using existing hashes; verify retries, distinct versions, and cross-workspace isolation. |
| 19 | `feat: extract text from PDF sources` | Add a bounded PDF parsing service with page-location metadata and fixtures for malformed, scanned, and multi-page documents. No API/UI expansion in this slice. |
| 20 | `feat: upload PDF sources with page provenance` | Connect PDF ingestion to storage/API and existing sources UI; split API and UI if needed. Do not present extracted-text offsets as original PDF byte offsets. |
| 21 | `feat: fetch research webpages safely` | Add a bounded fetcher with URL/address validation, redirect revalidation, timeouts, size limits, and tests preventing access to private/internal targets. |
| 22 | `feat: ingest webpage text with provenance` | Parse fetched content, retain location/version metadata, and expose explicit ingestion. Add the URL form in a separate commit if necessary. |
| 23 | `feat: persist versioned passage embeddings` | Add an embedding-provider interface and vector storage with model/dimension/version provenance; use deterministic fakes for tests. |
| 24 | `feat: generate passage embeddings in bounded batches` | Add explicit batch generation, completion state, retries, and deduplication. Verify partial failures and resumability. |
| 25 | `feat: add workspace vector retrieval` | Implement workspace-scoped nearest-passage retrieval with the same citation metadata contract; test using fixed vectors. |
| 26 | `feat: combine keyword and vector retrieval` | Add deterministic rank fusion, evidence deduplication, and answer-context integration. Compare against the keyword baseline before changing defaults. |
| 27 | `feat: rerank retrieved evidence` | Add an optional bounded reranker behind an interface, with fallback behavior and evaluation showing whether it improves retrieval. |

## Milestone 4: agentic research and compounding memory — complete

Do this after the manually initiated research loop is useful and measured. Each bullet is a separate commit-sized capability; model/API/UI integration may need additional splits.

- **28 — `feat: persist research runs and task states`:** introduce run/task records, explicit transitions, and recovery tests; keep orchestration in the existing application initially.
- **29 — `feat: execute research tasks with durable leases`:** add worker claims, checkpoints, expired-lease recovery, and idempotent task effects.
- **30 — `feat: enforce research execution budgets`:** persist attempt, concurrency, time, and model/tool budget controls; test that limits stop further work.
- **31 — `feat: cancel and resume research runs`:** add cooperative cancellation and recovery behavior, including interruption tests.
- **32 — `feat: plan bounded research investigations`:** validate planner-generated subtasks and permitted actions before scheduling; test with fake planners.
- **33 — `feat: record research task events`:** retain ordered tool/progress events with duration and failure metadata; exclude secrets and unrestricted payload logging.
- **34 — `feat: stream research progress to the browser`:** add resumable event delivery and a run progress view; split transport and UI if needed.
- **35 — `feat: persist claims and evidence relationships`:** store atomic interpretations separately from source passages, including supports/contradicts/mentions links and verification state.
- **36 — `feat: retrieve prior claims with their evidence`:** reuse workspace findings without treating generated claims as original sources; preserve access scoping and freshness metadata.
- **37 — `feat: track conflicting evidence and open questions`:** retain disagreements, superseded claims, and unresolved questions without overwriting historical evidence.
- **38 — `test: evaluate persistent research memory`:** compare the same tasks with and without prior evidence-backed findings, including quality, repeated retrieval, latency, and cost.

## Before multi-user or public hosting

Plan separate commits for authenticated identity, workspace ownership/membership, authorization on every read/write/retrieval path, upload/provider abuse limits, deployment configuration, and backup/restore verification. The current workspace scoping is not user authentication. Keep the local prototype local until these requirements have concrete implementations and tests.

## Recommended next action

Milestones 1–4 are implemented. Review the operations guide and measured evaluation limitations before choosing new work. Public or multi-user hosting still requires the separate identity, authorization, abuse-limit, deployment, and backup work listed above.
