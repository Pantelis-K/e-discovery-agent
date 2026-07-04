# E-Discovery Reviewer Cockpit — Technical Specification

**Purpose.** Build guide for a hackathon submission (UK AI Agent Hackathon EP5, Conduct.ai track). Reference document, not a linear read. Section 8 is the plan (now a progress checklist); sections 1–7 are the material the plan operates over.

**Reader assumptions.** Two technically literate builders, both new to agentic AI (one with minor prior exposure). Python and JavaScript comfort assumed. Familiarity with Django, React, and SQL assumed. No prior LLM tool-use loop experience assumed.

**Timeline.** Effective build window is ~2 days (see revision-3 note) with one teammate having limited daily availability. Scope reductions reflected in section 8.

**Amendment note (revision 1).** This spec was first updated after an architecture review conversation. Key revisions from that pass: the loop shape is queue-population-then-review (not search-per-document); `extract_entities` cut from the tool set; mid-batch intervention cut; discard-batch action cut; bulk reversibility UI cut; corrections viewer added; dev-vs-demo cost strategy added.

**Amendment note (revision 2 — corpus & topic pivot).** The data source and evaluation topic changed after direct verification against primary TREC sources and against the actual data on disk. Summary of the change, which touches sections 1, 3, 5, 6, 7, 8:

- **Corpus: CMU/CALO maildir → EDRM Enron v2 de-duplicated text bundle.** The original plan scored agent decisions against TREC qrels but ingested the CMU/CALO collection. TREC's qrels key to the EDRM collection, and TREC itself states no mapping exists between EDRM and CMU-family collections — so the planned "doc-id normalisation" rested on a crosswalk that does not exist. The EDRM v2 text bundle *is* the corpus the answer key was built on, so alignment is by construction.
- **Topic: "207 / Special Purpose Entities" → Topic 204 (document destruction / retention / shredding).** Verified from the TREC 2009/2010 overviews: Topic 207 is fantasy football; there is no SPE topic in the 201–207 set. Topic 204 was chosen for its non-technical legibility (a spoliation story a lay judge follows instantly), its healthy gold pool (~6,362 estimated relevant documents), and because it keeps privilege thematically central via legal-hold instructions from counsel.
- **Evaluation: score against the TREC 2010 Learning-task gold (`qrels.t10legallearn`), Topic 204, on the assessed pool, base-emails only, recall-first framing.** No manual labelling.
- **Data-structure realities** verified on disk and folded into sections 3, 5, 6: `From:`/`To:` are frequently missing; internal participants appear as Exchange X.500 distinguished names with no recoverable email address; there is no threading header; a small fraction of `.txt` files are binary-corrupted. See `DATA_REFERENCE.md` for the authoritative structural description; this spec references it rather than restating it.

## Amendment note (revision 3 — evaluation methodology, corrected benchmark facts, 2-day replan)

This revision was produced after verification against primary TREC sources (the
official TREC 2010 Legal Track overview, NIST-hosted qrels and evaluation toolkit
source code) and after the build window shrank to 2 days. Summary:

- **Corpus decision re-opened and re-confirmed.** EDRM v2 text + Topic 204 stands.
  Alternatives (CMU/CALO, EDRM XML ~74GB, other labelled corpora) all trade a solved
  extraction problem for an unsolved one (no ground truth, or a new multi-day data
  investigation). The extraction is no longer "messy": `DATA_REFERENCE.md` reduces it
  to seven deterministic loader rules. The hackathon brief explicitly rewards messy
  realistic data.
- **Benchmark facts corrected.** Topic 204 was one of the hardest TREC 2010 topics:
  the best system reached **29.8% recall at the 3% cut on Topic 204** (the previously
  cited ~50% was the best run's cross-topic average), and the best actual F1 on 204
  was **26.0%**. The estimated-relevant figure of ~6,362 is confirmed (6361.83 in the
  official `calc2.c`).
- **Evaluation methodology now fully specified** (was the biggest gap): a headless
  **eval mode** produces the accuracy number over the judged pool; the live loop
  produces the throughput/scale story. The two are reported as separate honest
  numbers; no end-to-end collection recall is claimed.
- **qrels format known in advance.** `qrels.t10legallearn.gz` (97MB) contains a row
  per document per topic: join key `topic:docid`, stratum ∈ {100, 1000, 10000,
  1000000}, rel ∈ {−1 unjudged, 0 non-relevant, 1 relevant}. Filter `rel ≥ 0` and
  topic 204; drop `.N` attachment ids. (Format confirmed on download — see §8 checklist.)
- **`seed.csv` identified**: the TREC 2010 Learning-task seed set. Never injected into
  prompts; any overlap with the judged eval pool is excluded from reported metrics.
  (Verified base-email counts corrected in revision 4 — see below.)
- **Plan recompressed to 2 days** (§8). Submission is repo + deck + recorded video —
  the recording is the deliverable, which removes live-failure risk and moves the
  build hard-stop to mid-evening Day 2.
- Additional cuts: `find_thread` fully cut; audit query bar cut; CN→display-name
  corpus map cut; single-decision reversal demoted to stretch.

See `decisions.md` (entry dated 2026-07-02) for the full context, options considered, and revisit conditions behind this pivot.

## Amendment note (revision 4 — FastAPI → Django framework pivot; streaming model; schema corrections)

This is the current revision. The backend framework changed from FastAPI to Django after Person B committed the pivot; this revision records the decision and reworks the sections that depended on FastAPI-specific mechanics. Touches sections 1, 2, 3, 4, 5, 6, 8. Summary:

- **Backend framework: FastAPI → Django (Django + Django REST Framework).** The project is now a standard Django project (`e_discovery_backend`) with three apps: `api`, `agent`, `documents`. The schema in §6 is realised as Django models with migrations as the source of truth.
- **Streaming model: synchronous `StreamingHttpResponse`, not async/ASGI.** The agent loop runs inside a Django streaming view as a generator that `yield`s SSE frames, under the standard multithreaded dev server (`manage.py runserver`, WSGI). No ASGI server (uvicorn/daphne) is required. This was a deliberate choice over async+ASGI: the ORM, `sentence-transformers`, `chromadb`, and the Anthropic SDK are all synchronous, so sync streaming avoids `sync_to_async` scattering and async-ORM rewrites for no demo-visible benefit. The SSE-not-WebSockets decision (§4) is unchanged.
- **Human-review pause: DB-polling, not `asyncio.Event`.** When the agent hands off, the loop persists a pending-review row and blocks, polling that row for a resolution written by a separate `POST`. This is more robust for the pausable/resumable requirement (pause state is a DB row, not in-memory) and works under WSGI.
- **Ingestion is now Django management commands** (`manage.py ingest_documents`, `manage.py embed_documents`) with parsing logic in `documents/parsing.py`, replacing the standalone `ingest.py`.
- **CSRF/CORS for the SPA.** Reviewer-action `POST`s are cross-origin (Vite `:5173` → Django `:8000`). CORS is handled by `django-cors-headers`; the API views are `csrf_exempt` (no auth in the demo) so unsafe-method POSTs don't 403.
- **WAL under Django** is enabled via a `connection_created` signal running `PRAGMA journal_mode=WAL` (§6).
- **Schema corrections (§6)** — the intended shape was already correct in the spec; the current Django models diverge and must be brought into line: `AgentStep` is missing `error`/`tokens_input`/`tokens_output`; `Correction` is missing `summary`; `AuditEvent.payload` is a 255-char field and must widen to JSON/TEXT. New: `AgentRun.run_type` (`live`/`eval`) for eval mode, and eval mode upserts `Document` rows to satisfy the `Decision.doc_id` FK while remaining decoupled from full-corpus ingestion.
- **Verified counts corrected (§5).** Topic 204 judged base-email pool = **387 relevant + 1,641 non-relevant = 2,028** (disk join 2,028/2,028). `seed.csv` Topic 204 base = **44 relevant + 437 non-relevant = 481** (the earlier 1,191 counted attachments). Seed∩judged overlap = **47** doc-ids (`overlap_excluded.txt`). Topic 202 fallback **evaluated and dismissed** (387 ≫ the ~150 trigger). A **~89.7% recall ceiling** (347/387) applies to Metric 1 (40 header-only records judged relevant via subject-string collision).
- **Section 8 replaced** with a topic-grouped progress checklist (done / partial / not-started) in place of the day-by-day plan.

See `decisions.md` (entry dated 2026-07-03) for the full context, options considered, and revisit conditions behind the framework pivot.

---

## 1. System overview

The system is five components running together, four of them on the reviewer's laptop for the demo. In order of dependency: a **SQLite database** holds all persistent state; a **Chroma vector index** holds embeddings of email chunks and answers similarity queries; a **Django backend** (Django + Django REST Framework) hosts the agent loop, the tool implementations, and an SSE endpoint that streams events to the browser; a **React frontend** renders the reviewer cockpit and consumes the SSE stream; the **Anthropic API** is called from the backend as the orchestrator LLM and (separately) as the classifier LLM inside one of the tools.

Direction of dependency is one-way in most places. The frontend talks to the backend over HTTP (for actions like starting a run, submitting a correction, resolving a handoff, committing a decision) and over SSE (for the stream of agent events flowing the other way). The backend reads and writes SQLite directly (through the Django ORM), reads Chroma directly, and calls the Anthropic API outbound. Chroma and SQLite do not talk to each other; the backend is the only thing that touches both.

Two things are worth noting about what does *not* exist in this architecture. There is no message queue — the agent loop runs synchronously inside a single Django streaming view (`StreamingHttpResponse` over a generator), streaming as it goes. There is no separate worker process for embeddings or ingestion; ingestion is a one-shot management command run before the demo, not a live system. Both simplifications are deliberate cost-cutters that we recover from in section 8 if they cause pain.

Deployment shape: everything runs on one laptop during the demo. Backend on `localhost:8000` via the Django dev server (`manage.py runserver`, WSGI — no ASGI server needed), frontend on `localhost:5173` via Vite dev server, SQLite file on disk, Chroma persistent directory on disk. We do not deploy to Railway/Render/Vercel. The reasoning is that hosting adds a day of yak-shaving (env vars, build pipelines, cold starts, CORS, SSE proxying quirks on serverless platforms) for a demo that is going to be shown live from a laptop screen anyway. If hosting later becomes desirable — for judges to poke at post-submission — Railway with a Dockerfile is the least painful option, but that is a stretch goal.

A canonical request flow, sketched so it can become a sequence diagram. Reviewer clicks "Start review on Topic 204 (document destruction & retention)": the frontend `POST`s to `/runs`, the backend inserts a row into `agent_runs` and returns the `run_id`. The frontend then opens an `EventSource` on `GET /runs/{run_id}/stream`; that streaming view enters the agent loop and streams events back as they happen. First iteration: orchestrator LLM is called with the system prompt, the goal, and empty history; it returns a tool call, say `search_documents("document retention deletion shredding preserve", filters={})`. Backend executes the tool (Chroma query, returns 20 doc IDs with scores), writes an `agent_step` row, and `yield`s a `step_completed` SSE event to the frontend. Second iteration: orchestrator called again with the prior tool call and result appended to its history; it decides to `read_document(doc_id="3.818908.A0CV...")`; backend fetches from SQLite, writes a step, streams the event. And so on until a stop condition fires (see section 2).

That loop is the product. Everything else — the UI, the schema, the tools — exists to serve it.

---

## 2. Agentic architecture

### The loop

One iteration of the loop is a single call to the orchestrator LLM followed by execution of at most one tool. The orchestrator LLM is given a prompt containing four things: the system prompt (its role, the review goal, the rules of engagement), the current state summary (queue position, remaining budget, recent corrections), the transcript of prior iterations in this run (each iteration = tool call + tool result), and the tool schema. It responds with either a tool call or a special `finish_batch` signal.

The backend parses the response. If it is a tool call, the tool is executed, the result is captured, and the loop proceeds to the next iteration with the tool call and result appended to the transcript. If it is `finish_batch`, the loop exits and the backend waits for the reviewer's next instruction (typically "approve batch" or "start next batch").

Concretely: use Anthropic's native tool use. The tools are declared in the API call, the model returns `tool_use` content blocks, we execute them, and pass `tool_result` blocks back in the next call. Do not build a custom "the model outputs JSON we parse" layer — Anthropic's tool use handles the parsing, retries on malformed calls, and is battle-tested. This is one of the two or three most important stack choices in the build and it saves roughly half a day.

### Two phases within a run

The loop is a single mechanism, but the orchestrator's behaviour naturally divides into two phases per batch. The distinction matters for reasoning about tool call patterns and for cost estimation.

**Phase 1: Queue population.** At the start of a batch, the orchestrator issues one or several `search_documents` calls to build the candidate pool. It may vary the query terms ("document retention policy", "shredding destroy records", "litigation hold preserve emails", "delete files instructed") to broaden coverage, and may apply filters by date range or custodian. The union of results, deduplicated and filtered against already-reviewed documents (see section 3), becomes the batch queue. Typically 3–5 orchestrator turns.

**Phase 2: Per-document review.** The orchestrator picks the next document from the queue, calls `read_document`, calls `check_privilege_signals` as needed based on what it sees, calls `classify_relevance`, proposes a decision, and moves to the next document. `search_documents` is not called during this phase in the normal case. The exception is when the agent reads a document and encounters a new angle or reference it wants to explore (e.g. finds mention of a specific records-management project it hadn't queried for) — it can issue an additional search that adds to the queue. This should be rare in practice and each such expansion is logged as a distinct event.

The phase distinction is not enforced by the code — the LLM is free to search whenever it wants — but the system prompt should instruct it in this shape, and the observed behaviour should match.

### What lives in the orchestrator's context

Each iteration's orchestrator call includes:

- **System prompt.** Fixed for a run. Contains the role ("you are an e-discovery review agent"), the specific topic and its criteria (for the demo, Topic 204: documents relating to the alteration, destruction, retention, lack of retention, deletion, or shredding of documents or other evidence), the privilege triage stance (conservative, over-inclusive), the batch-size target, and the instruction to stop and call `request_human_review` under specified conditions.
- **Recent corrections.** A rolling list of the last N (start with N=10) corrections the reviewer has made in this run, injected as natural-language notes. This is our corrections-propagation mechanism. Each correction is one or two sentences: "Correction: a routine IT email about the standard email-retention *schedule* is not responsive — Topic 204 is about destruction/retention in the context of evidence or litigation, not ordinary records lifecycle." See below.
- **Run transcript.** The sequence of tool calls and tool results from prior iterations in this run. Truncate aggressively — see the token budget note below.
- **Current document context.** When the agent is working on a specific document (post-`read_document`), that document's text is part of the recent transcript. When it moves on, older document contents fall out of the truncation window.
- **Tool schema.** The list of tools available, injected by the Anthropic SDK when we declare them.

### What persists in SQLite between iterations

Everything the loop can be resumed from. See section 6 for schema. The important claim here is: the loop can be killed at any point (crash, reboot, deliberate pause) and restarted from the last completed step by reading the `agent_steps` table for the current run and reconstructing the transcript. This is the "pausable and resumable" non-negotiable, and it is cheap if the schema is right from day one.

### Stop conditions

The loop exits or pauses on any of:

1. **Batch complete.** The agent has proposed decisions for the target batch size (default 25 documents, 5 during development) and returns `finish_batch`. Loop exits; reviewer takes over for batch review.
2. **Explicit human handoff.** The agent calls `request_human_review(doc_id, reason)` on a specific ambiguous document. Loop pauses, reviewer sees the document with the reason, resolves it inline, and the loop resumes with the resolution appended to the transcript.
3. **Confidence floor breach.** If the agent proposes a decision on a document with confidence below a threshold (default 0.6), the backend intercepts, converts it to a `request_human_review`, and pauses. This is a backend rule, not something the LLM decides — it's a hard constraint we impose to make the "user in control" story true even if the model would happily push through.
4. **Error budget exhausted.** If any single tool errors more than 3 times in a run, or the LLM returns 3 consecutive malformed calls, the loop halts and surfaces to the reviewer. Not silently retried forever.
5. **Iteration cap.** A hard limit of, say, 100 iterations per batch to prevent runaway loops. Should never fire in normal operation; if it does, something is wrong and we want to see it.

**Note on mid-stream intervention.** Earlier drafts of this spec included a "reviewer proactively grabs the wheel mid-batch" flow. Cut. Corrections happen at (a) explicit human-review handoffs and (b) batch boundaries. During an active batch the reviewer can inspect anything read-only, and can pause the loop entirely, but cannot correct in-flight proposals until the batch completes or the agent hands off. This simplifies state management significantly. The tradeoff: a correction can't propagate to documents *within the same batch*, only to the next. In a 25-doc batch running a few minutes end-to-end, this is a non-issue.

### How the streaming loop and the human-review pause work under Django (Option 1)

Because this is the part most affected by the FastAPI→Django pivot, spell it out:

- The loop **is** the body of the `GET /runs/{run_id}/stream` streaming view. The view returns a `StreamingHttpResponse` wrapping a Python generator; each SSE event is a `yield` of a `text/event-stream`-formatted frame. There is no separate `emit_sse` side channel in the simplest form — emitting an event is yielding it. (If a tool needs to emit sub-events, have it push onto an in-process queue the generator drains between iterations.)
- This runs under the standard multithreaded dev server (`runserver`, WSGI). No `asyncio`, no ASGI server. The Anthropic SDK, ORM, Chroma, and embedder calls are all synchronous and run inline in the generator.
- **Human-review pause (replaces the asyncio.Event pattern):** when `request_human_review` fires (or the backend auto-converts a low-confidence proposal), the loop writes a pending-review row to the DB, streams a `human_review_requested` event, then enters a short polling wait — sleep a fraction of a second, re-query the pending-review row, repeat — until a separate `POST /runs/{run_id}/resolve` writes the reviewer's resolution. Because `runserver` is multithreaded, the resolving POST is served on another worker thread while the stream request is parked. The pending review is persisted **before** the loop blocks, so a crash mid-wait recovers from the DB row (resumability preserved).
- Concurrency footprint: one long-lived stream request plus occasional short action POSTs. WAL mode (see §6) lets the POST writes proceed while the stream reads. A single reviewer, a single active run — no contention beyond this.

### Eval mode (headless)

A separate execution path, `run_eval.py`, exists solely to compute the accuracy
metric. It is not the cockpit loop:

- **No orchestrator, no Chroma, no human gates.** For each judged Topic-204
  base-email doc-id (from the qrels), read the document text directly (via the
  doc_id→path index built at ingestion; SQLite if already ingested, raw file
  otherwise), call `classify_relevance` (Haiku, prompt v1 — the same versioned prompt *and the same run-level criterion* the cockpit uses), and record the proposed decision.
- **Bypassing the human-commit gate is deliberate and defensible**: eval mode
  measures the classification component; nothing it produces is a "committed"
  decision. Eval writes to `decisions` under an `AgentRun` whose `run_type='eval'`,
  with `committed=0` forever.
- **Document-FK handling.** `Decision.doc_id` is an FK to `Document`. Eval mode
  upserts a minimal `Document` row for each judged doc-id from the raw file it just
  read, then writes the `Decision`. This keeps eval **decoupled from full-corpus
  ingestion** — only the ~2,028 judged docs need to be readable on disk — while
  satisfying referential integrity and letting eval decisions be inspected in the
  same UI.
- **Resumable**: skips doc-ids that already have an eval decision, so a crash or
  rate-limit stall costs nothing.
- **Concurrency 5 with exponential backoff** (tier-1 input-token limits are the
  binding constraint; expect roughly 25–50 docs/min on Haiku).
- **Body truncation at ~6,000 characters** for cost control (log when truncation
  fires).
- A companion `report_eval.py` computes recall, precision, F1, and the confusion
  counts, and writes `results.json` — the numbers that go on the results slide.
  It subtracts the 47 seed∩judged overlap doc-ids (`overlap_excluded.txt`) from the
  reported metrics.
Key property: **eval mode does not depend on full-corpus ingestion or embeddings.**
Only the ~2,028 judged documents need to be readable on disk. The accuracy number
survives even if the overnight embedding run fails.

### Corrections propagation (context injection)

When the reviewer overrides an agent decision, the frontend sends the correction to `POST /corrections` with the doc ID, the field corrected (relevance, privilege, issue tag), the new value, and a free-text rationale. The backend does two things: writes a `corrections` row, and generates a one-or-two-sentence natural-language summary of the correction using a small LLM call (or a template — start with a template, upgrade to an LLM summary if templates are too rigid). This summary is stored in the `corrections.summary` field and joins the rolling list of recent corrections.

On the next orchestrator iteration, the recent corrections list (last N, default N=10) is inserted into the system prompt under a heading like "Recent guidance from the reviewer — apply these to similar cases." The agent sees them and, empirically, applies them to subsequent similar documents. This is the crude method: token-wasteful, non-deterministic in application, and it degrades once the correction list gets long. It is also two hours of work and demos beautifully because you can watch the correction land and then watch the next document reflect it in the reasoning trace.

**Corrections viewer.** The reviewer must be able to see exactly what corrections are currently in the agent's context. This is a first-class UI feature — either a panel in the cockpit or a modal reachable from the audit timeline. It shows the literal text (`corrections.summary`) being injected into the system prompt right now, with timestamps and links back to the documents each correction originated from. This directly answers the question "what does the agent currently believe you've told it?" — a question a judge or an auditor will ask. Small UI feature, high defensibility payoff.

**Future work on the corrections mechanism.** Two distinct improvement paths, both worth mentioning in the presentation.

- *Large cap with LLM resummarisation.* The N=10 cap is a token-cost concession; in real use, reviewers would rightly expect their older corrections to still influence the agent. The upgrade path: allow the correction list to grow to a much larger cap (say 100), and when it reaches the cap, invoke an LLM pass that consolidates similar corrections into merged rules and drops truly stale ones. This keeps the natural-language architecture but removes the "silently forgot your earliest correction" bug.
- *Structured rule memory.* The more architecturally clean approach. Extract structured rules from corrections ("documents mentioning the standard retention schedule with no litigation context → not responsive", "legal-hold instruction from counsel → privileged") and apply them deterministically before or alongside the LLM's judgment. More engineering, more principled, better long-term. This is the "what we'd build next" item in the presentation.

### Token budget and cost strategy

A single orchestrator call could balloon fast: prior transcript, document contents from prior iterations, corrections list. We need aggressive truncation. Rules:

- Keep the last 3 iterations of the transcript in full (including document body if the current document is in focus).
- Drop everything older entirely. No one-sentence summaries, no running summary. If experience shows the agent making stupid mistakes from lack of context, add a rolling summary back — but start without it.
- When a document is "in focus" (recent `read_document`), keep its full text. When focus moves to the next document, the old document body drops out of the truncation window.
- Cap the corrections list at N=10 for the demo. See future work note above.

**Dev vs demo cost strategy.** Cost during development iteration is a real concern. Levers, in order of impact:

1. **Haiku for the orchestrator during dev, Sonnet for evaluation runs and the demo.** Haiku is ~12x cheaper on input. One-line change. Occasional dumber decisions but the loop mechanics are identical. Use Haiku from day 1 of development.
2. **Haiku for `classify_relevance` always.** Even in the demo. The classification prompt is narrow and structured; Haiku handles it well and roughly halves the per-run LLM cost.
3. **Batch size 5 during dev, 25 during demo/evaluation.** Config variable from day 1. Also drastically improves iteration speed.
4. **Aggressive transcript truncation as above.** Do not add summary layers unless empirically necessary.

Combining all four: a dev batch should cost well under $0.50. A full demo/evaluation run under $5. Track token usage per run and log it (via `agent_steps.tokens_input`/`tokens_output`); the numbers should confirm this. If they don't, the truncation isn't working.

Practical target: keep each orchestrator call under 15K input tokens.

### Failure modes

- **Tool errors** (Chroma unavailable, missing document, malformed input) return an error object to the LLM as the tool result. The LLM sees the error and typically retries with a corrected call. If the same tool fails 3 times, we halt. The error is recorded in `agent_steps.error`.
- **Malformed tool calls** are handled by Anthropic's SDK — the model can course-correct. If we see 3 malformed calls in a row, halt.
- **LLM refusals** ("I cannot make a legal judgment") are rare with a well-scoped system prompt but possible. Mitigation: the system prompt is explicit that the agent is making a *proposed classification for human review*, not a legal opinion. If a refusal happens, log it, skip the document, and surface it in the audit log.
- **Rate limits.** Anthropic's tier-1 rate limits are generous but not infinite. Real risk during evaluation runs where we might make thousands of calls. Mitigation: exponential backoff on 429s built into every LLM call, and a run-level concurrency cap of 1 (never run two batches simultaneously).

---

## 3. Tool specifications

Six tools (one — `find_thread` — cut from build scope in revision 3; `extract_entities` cut in revision 1). For each: signature, data source, deterministic vs LLM, latency expectation, error behaviour.

The general design principle: tools should have crisp responsibilities and be independently testable. The LLM's job is orchestration; the tools' job is competent execution of narrow capabilities. Where a tool could plausibly be "the LLM does it inline" versus "we make it a tool," we make it a tool. Two reasons: it isolates the classification logic so we can version and evaluate it separately, and it produces cleaner audit records because every classification is a discrete logged event with structured inputs and outputs.

### `search_documents`

**Signature.** `search_documents(query: str, filters: dict = {}) -> list[SearchHit]` where each hit is `{doc_id, score, snippet, sender, date}`.

**Data source.** Chroma vector index over email chunks (base-email documents only — see section 5). Filters passed to Chroma's `where` clause: `date_range`, `sender_domain`, `custodian`.

**Deterministic or LLM.** Deterministic. Query is embedded with `sentence-transformers/all-MiniLM-L6-v2`, top hits returned. No LLM in the loop for this call.

**Review-state filtering.** Critical. The tool implementation MUST exclude documents that already have a committed decision for the current run, AND documents already in the current batch's queue (proposed but not yet committed). Otherwise the agent will pull the same document into successive batches or into the same batch twice. Implementation: fetch top 50 hits from Chroma, exclude via an ORM lookup against the `decisions` table filtered by `run_id`, return top 20 of what remains. Both the run and the current batch ID are passed in from the loop context, not by the LLM.

**Note on `sender`.** The hit's `sender` field may be null for a meaningful fraction of documents — many records lack a parseable `From:` line (see section 5). Return what is available; the agent and UI must tolerate a missing sender.

**Latency.** Sub-second on the Enron corpus with a warm Chroma instance, plus a fast SQLite filter step.

**Errors.** Empty results returned as empty list, not an error — this is a valid outcome the LLM should handle (it should try a different query or `finish_batch`). Chroma unavailability returns an error object; the LLM will likely retry with a different query.

**Example call.** `search_documents("shred destroy documents retention hold", filters={"date_range": ["2001-09-01", "2002-03-31"]})` → list of up to 20 hits, all previously-unreviewed for this run.

### `read_document`

**Signature.** `read_document(doc_id: str) -> Document` where Document is `{doc_id, subject, from, to, cc, from_display, to_display, cc_display, date, body, custodian, attachments}`.

**Data source.** SQLite `documents` table (via the `Document` model).

**Deterministic or LLM.** Deterministic. Straight ORM fetch.

**Field-availability reality.** `subject`, `from`, `to`, and `cc` are frequently absent in this corpus and will be returned as null / empty when the source message did not carry them (see section 5 for measured prevalence — `From:` present ~83%, `To:` ~66%, and much lower for some custodians). `date` is always present. The agent's prompt must be told these can be missing so it does not over-interpret a blank `from` as anonymity. `attachments` is always an empty list in the demo build — attachment documents are out of scope (defer list), and we ingest base emails only; the field exists for shape compatibility only.

**Resolved participant units (`*_display`).** Alongside the raw `from`/`to`/`cc` strings, `read_document` returns the deterministically resolved participants: `from_display` is one unit object (or null), `to_display` and `cc_display` are lists. Each unit is `{raw, display, kind, cn_code, email, domain}` where `kind` is one of `x500_named`, `smtp_prefixed`, `smtp_internal`, `smtp_external`, `bare_name`, `x500_blank`, `other`, and `display` is a reviewer-safe label (`"(Unresolved)"` for `x500_blank`/`other`). Resolution runs deterministically at ingest via `documents/participants.py` (see §5); the raw strings are kept alongside for audit. See §5 for how the resolver handles the three coexisting address forms and its known limitations.

**Latency.** Milliseconds.

**Errors.** Missing doc ID returns an error object. Should never happen if the LLM is calling with IDs from search results.

### `find_thread` — CUT from build scope (revision 3)

**Signature.** `find_thread(doc_id: str) -> Thread` where Thread is `{thread_id, messages: [Document], confidence: str}` in chronological order.

**Data source.** SQLite. **Important reality (verified on disk):** the EDRM text corpus contains **no `Message-ID`, `In-Reply-To`, or `References` header** — there is no structured field for reconstructing reply/forward chains. Threading is therefore *heuristic and best-effort only*, precomputed during ingestion from normalised subject line + participant overlap + temporal proximity. It is not reliable, and the returned `confidence` field ("high" / "low") must communicate this.

**Deterministic or LLM.** Deterministic (heuristic grouping).

**Latency.** Milliseconds.

**A more reliable forward signal lives in the body.** Roughly 15% of documents contain inline `-----Original Message-----` or `Forwarded by …` blocks in the body text itself. For detecting that a message *is* a forward or reply, and reading the original content, the agent reading the body directly (via `read_document`) is more dependable than `find_thread`. The system prompt should lean on this: treat inline forwarded/quoted body content as the primary evidence of a chain.

**Errors.** If no plausible thread is found, returns a Thread containing only the single message with `confidence: "low"`. This is a valid outcome, not an error.

**Status.** Cut entirely in revision 3 — threading is unreliable here and inline body content substitutes. `thread_id` remains in the schema (populated best-effort at ingestion, may be self) but no tool surfaces it. The `context_signals.is_forwarded` flag in `check_privilege_signals` (from inline body markers) carries the forward signal instead.

### `extract_entities` — CUT from build scope

Removed in revision 1 and still cut. Reasoning: in mental simulation of typical flows, the orchestrator rarely calls this tool — participant information and content signals available from `read_document` and `check_privilege_signals` cover most cases where entity awareness would matter. The tool is more useful as a UI display feature ("show people mentioned in this email") than as an agent tool. Cost of building it does not clear the benefit within the timeline. Mention as a future work item if entity-based cross-referencing becomes desirable.

### `check_privilege_signals`

**Signature.** `check_privilege_signals(doc_id: str) -> PrivilegeSignals` where PrivilegeSignals is:

```
{
  participant_signals: {
    known_lawyers_in_from: [{name, via, matched}],   // via ∈ {cn_code, email, display}
    known_lawyers_in_to:   [{name, via, matched}],
    known_lawyers_in_cc:   [{name, via, matched}],
    external_counsel_domains: [str],
    participants_unresolved: bool     // true unless BOTH From AND To carry ≥1 matchable participant
  },
  content_signals: {
    has_confidentiality_marker: bool,
    has_legal_advice_language: bool,
    matched_phrases: [str]
  },
  context_signals: {
    is_forwarded: bool,               // detected from inline body markers
    thread_confidence: "high" | "low"
  },
  overall_signal_strength: "none" | "weak" | "moderate" | "strong"
}
```

Each lawyer match is a structured object (`{name, via, matched}`) rather than a bare name string so the audit trail records **which key hit** — an auditable "Shackleton via cn_code=Sshackl in From" beats an opaque "['Shackleton']".

**Data source.** All signals are computed **live at call time** — there is no precomputed
`privilege_signals` cache (dropped; see §6). SQLite (via `read_document`'s resolved
participant units `from_display`/`to_display`/`cc_display`, plus body), plus a hardcoded
list of known Enron in-house counsel and external counsel domains. Content regex over the
body for phrases like "privileged and confidential," "attorney work product," "seeking legal
advice," and — relevant to Topic 204 — "litigation hold," "preservation notice," "do not delete."

**Deterministic or LLM.** Deterministic. Explicitly not LLM-based. Rationale: this tool exists precisely so the privilege triage logic is auditable and defensible. If a judge later asks "why did you flag this as privileged," the answer is a structured signal set, not "the LLM said so." The LLM interprets the signals into a decision, but the signals themselves are produced by transparent rules.

**Structural matching (revised from substring, decision 2026-07-04).** Each resolved
participant unit is matched against `LAWYERS` **structurally**, on the unit's fields, not
by scanning the raw text:

1. `cn_code` exact (case-insensitive) — an Exchange CN code is a person key → **high confidence**, `via: "cn_code"`.
2. `email` exact (case-insensitive) → **high confidence**, `via: "email"`.
3. `display` `token_subset_match` against a lawyer variant (every variant token appears in the observed display) → **low confidence**, `via: "display"`. Surname-collision-prone (e.g. Tana Jones vs Karen Jones), so this alone is a weak signal.

Exact wins over display across ALL lawyers (the two passes are separated). Matches are
deduplicated within a field. External-counsel domains come from each unit's `domain` field
matched against `EXTERNAL_COUNSEL_DOMAINS`.

**`participants_unresolved` semantics (refined 2026-07-04).** True unless BOTH `From` **and**
`To` carry at least one participant with `kind ∈ {x500_named, smtp_prefixed, smtp_internal,
smtp_external, bare_name}`. A field that is missing, or present but composed entirely of
`x500_blank`/`other` units (undisclosed-recipients, suppression labels), is not usable. This
fires more often than the previous "true only when both missing" rule (~40% of docs are
now flagged unresolved) — chosen deliberately for the conservative privilege stance: "no
lawyer found" must not read as "not privileged." Positive lawyer findings still coexist
with the flag; the flag says "the participant sample was thin," not "no signal."

**Address-matching reality (from the participant-format survey — `docs/participant-format-survey.md`).**
Internal Enron participants appear in three coexisting forms across the corpus: (1) clean
SMTP `name@enron.com`, (2) Exchange X.500 DN `Name </O=ENRON/OU=…/CN=RECIPIENTS/CN=CODE>`,
(3) bare display name with no address. `smtp_prefixed` is the single largest category
(40.0% of all participant units, so SMTP-based matching gets substantial coverage).
Critically, **no `@enron.com` address exists anywhere in the corpus for an X.500-addressed
person** — a `CN=CODE` fragment resolves to a *display name* only, never an email.
Consequences:

- The lawyer list must carry, per lawyer, **all three keys**: `display_variants`, `cn_codes`, and `emails`. Matching succeeds on any one form. `cn_codes` are the piece that cannot be guessed; `manage.py suggest_lawyer_cn_codes` mines candidates from the resolved units (§5) and prints them for eyeballing.
- The corpus-wide `CN → display-name` **registry stays cut** (revision 3 decision reinforced 2026-07-04). Rationale strengthens: the survey found exactly **one** `x500_blank` unit in the whole corpus (i.e. one case where a DN has no accompanying display prefix to pair to), and even that one is a splitter artifact from a lowercase-`</o=` value — so a corpus-wide CN registry now has effectively zero remaining use case. The 10-lawyer hand-carry via `suggest_lawyer_cn_codes` covers the demand.

**Latency.** Milliseconds.

**Errors.** None expected; degrades to empty participant signals with `participants_unresolved: true` on missing metadata.

**The `overall_signal_strength` field** is a rules-based aggregate (a hint to the LLM, not a decision) with weighting refined 2026-07-04 to reflect confidence tiers:

- **`none`**: no content signals and no participant signal.
- **`weak`**: one content signal alone; OR a display-only lawyer match alone (collision-prone).
- **`moderate`**: two content signals with no participant; OR a high-confidence participant (cn_code / email / external-counsel domain) alone or with one content signal.
- **`strong`**: a high-confidence participant plus two content signals; OR both an in-house lawyer AND an external-counsel domain plus content.

The refinement matters because a display-only lawyer match, on its own, is not enough evidence to bump strength — surname collisions in a corpus this size are real.

### `find_participant_documents` — NEW (added 2026-07-04)

**Purpose.** A scoped participant-name lookup: given a person name, return documents where that name appears in `From:`, `To:`, or `Cc:`. Structured lookup over SQLite — deliberately separate from the semantic `search_documents` (Chroma) tool. Used when the reviewer or the agent has a specific person to trace (e.g. "show me everything from Sara Shackleton in the queue") or when a correction names an individual and the agent needs to find similar-participant cases without hallucinating that a semantic body-text query will surface them.

**Signature.** `find_participant_documents(name: str, fields: list[str] = ["from", "to", "cc"], limit: int = 50) -> list[ParticipantHit]` where each hit is `{doc_id, matched_in: [str], matched_unit: {kind, display, cn_code, email}, subject, date, custodian}`.

- `name` — a person's name in any natural form (`"Sara Shackleton"`, `"Shackleton, Sara"`, `"Shackleton"`).
- `fields` — subset of `{"from", "to", "cc"}`. Default all three.
- `limit` — cap on returned hits (default 50). Ranked by date DESC.
- `matched_in` — the fields in which this doc's units matched (a doc where the name is in both From and Cc gets `["from", "cc"]`).
- `matched_unit` — the first matching unit's structured representation, so the caller knows *which* form ("via CN=Sshackl" vs "via display 'Shackleton, Sara M.'") produced the hit — this is the audit trail.

**Data source.** SQLite `documents_document`, matching against the resolved `from_display`/`to_display`/`cc_display` unit JSON columns (populated by ingest / the corrective backfill; see §5). No Chroma, no LLM.

**Match rule.** `name_tokens(name)` must be a subset of `name_tokens(unit.display)` — the same `token_subset_match` used by `check_privilege_signals` for lawyer-display matching. Order-independent (`"Sara Shackleton"` and `"Shackleton, Sara"` both work as queries), tolerant of middle initials in the target (`"Shackleton, Sara M."` matches both), and directional to avoid surname-collision false positives (bare `"Shackleton"` as a query matches everything with that surname; bare `"Shackleton"` as a target does NOT match a query with a first name). The query side can also be an email prefix or a CN code — if `"@"` is present it matches against `unit.email` (case-insensitive exact), and if the query looks like a CN code (`re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name)` when no space present) it also matches against `unit.cn_code`. Display-token match is the default and covers the natural case; email/cn short-circuits are for advanced queries.

**Deliberately NO canonical person IDs.** The corpus has no directory table; the same person appears as X.500 DN with CN code, as SMTP address, as bare display name, and often with typo/space variants. Building a canonical identity registry would require corpus-wide clustering with no ground truth to score against, on a hackathon budget. Instead: match by string tokens, return the matching UNIT so the caller sees which form hit, and let the reviewer adjudicate whether two hits are the same person. This is the honest position — the identity resolver failure would be an own-goal on the "conservative, auditable" story.

**Deterministic or LLM.** Deterministic. Straight SQLite query + Python filter.

**Latency.** ~O(n) over `Document.objects.filter(<field>__icontains=name_token)` narrowed by SQLite, then a Python-side `token_subset_match` refinement over ~1–2K candidate rows. Sub-second on the full corpus for a typical name query. If it proves slow after full ingest, add a normalised participant-token table as an index (deferred).

**Review-state filtering.** Same discipline as `search_documents`: exclude doc_ids that already have a committed decision for the current run, and doc_ids already in the current batch's queue. Both IDs are passed from the loop context (not by the LLM).

**Errors.** Empty result → empty list (valid, LLM should try a related name or move on). Malformed `fields` (unknown field name) → error object; LLM course-corrects.

**Why this is separate from `search_documents`.** Structured vs semantic. `search_documents` runs a Chroma similarity query on chunk embeddings — it finds documents whose *body content* is semantically similar to a query string. `find_participant_documents` runs a SQLite lookup on structured participant metadata — it finds documents whose *sender/recipient set* contains a specific person. They answer different questions. Conflating them (e.g. "search for Shackleton" over Chroma) makes retrieval unreliable because the body may not mention the person at all when they are only the sender; conversely, semantic body queries should not be blurred with participant filters through Chroma's `where` clause because the participant metadata in Chroma is a display-hint only (§5, `extract_sender_display`), not the authoritative resolved unit.

**Relationship to the cut `extract_entities` tool.** Adjacent, but not the same. `extract_entities` (cut revision 1) was framed as "the LLM asks 'give me people mentioned in this document'" — an LLM-in-the-loop entity extractor over free text. `find_participant_documents` is the inverse and is deterministic: given a person, return docs. The rev-1 cut argued the LLM rarely needs entity extraction. The 2026-07-04 addition argues that a person-scoped retrieval capability *is* needed once corrections start naming individuals — but that need is served by structured lookup, not by extracting entities from body text.

**Example calls.**

- `find_participant_documents("Sara Shackleton")` → docs where Shackleton appears as sender or recipient in any of the three forms (SMTP via `sara.shackleton@enron.com`, X.500 via `CN=Sshackl` once populated, or display "Shackleton, Sara M."), ranked by date.
- `find_participant_documents("Shackleton, Sara", fields=["cc"], limit=20)` → last 20 docs where she's Cc'd.
- `find_participant_documents("Sshackl")` → CN-code short-circuit; docs where any unit has `cn_code == "Sshackl"` (case-insensitive).

**Status.** Not yet implemented (`documents/participants.py` provides the matcher primitives; the tool wrapper + API surfacing is TODO — §8 checklist).

### `classify_relevance`

**Signature.** `classify_relevance(doc_id: str, criteria: str) -> RelevanceJudgment` where RelevanceJudgment is `{relevant: bool, confidence: float, reasoning: str, key_passages: [str]}`.

**Data source.** SQLite for the document; separate LLM call with a classification-specific prompt.

**Deterministic or LLM.** **LLM-powered.** This is the one tool that internally calls the Anthropic API. The classification prompt is fixed and versioned (call it prompt v1, stored as a constant in `agent/prompts.py`). It takes the document text and the criteria and returns structured output. For the demo, `criteria` is the Topic 204 production request: documents relating to the alteration, destruction, retention, lack of retention, deletion, or shredding of documents or other evidence.

**Who supplies the criterion (decided 2026-07-03).** The criterion is run-level
configuration, not a per-call decision by the orchestrator. There is one topic per
run (multi-topic is deferred), so the criterion is constant for the run. The **Python
function** `classify_relevance(doc_id, criteria)` still takes `criteria`, but the
**LLM-facing tool schema exposes only `doc_id`** — the loop/dispatch injects the run's
canonical criterion (`AgentRun.criteria`) when calling the tool. This guarantees the
cockpit classifier and eval mode score the *identical* criterion (not just the
identical prompt v1), removes drift from the orchestrator paraphrasing a ~50-word
string on every call, and saves tokens. Consequence, made explicit: the classifier is
**corrections-blind by design** — reviewer corrections act at the orchestrator/proposal
layer (see §2 corrections propagation), never inside `classify_relevance`. See
`decisions.md` (2026-07-03).

**Why this is a tool rather than something the orchestrator does inline.** Three reasons. First, it lets us version the classification prompt independently of the orchestrator prompt. Second, every classification produces a discrete audit record with structured inputs and outputs, which is central to defensibility. Third, it lets us swap the underlying model — we run the orchestrator on Sonnet (demo) and the classifier on Haiku for cost, without changing the loop.

**Latency.** 2–5 seconds per call.

**Errors.** Structured output is obtained via a **forced `record_judgment` tool call**
(`tool_choice` pins the tool to the RelevanceJudgment schema), so the output shape is
enforced up front — there is no JSON-fence-stripping and no malformed-output retry path.
The returned `.input` dict is defensively coerced (confidence clamped to [0,1],
`key_passages` forced to a string list). Remaining error modes: LLM refusal (rare —
handled as above), rate limits / 529 overload (exponential backoff with jitter, error
after MAX_RETRIES), and the near-impossible empty-tool-block case (treated as a hard error).

### `request_human_review`

**Signature.** `request_human_review(doc_id: str, reason: str) -> HumanReviewResult` where HumanReviewResult is `{decision: dict, reviewer_notes: str}`.

**Data source.** This tool pauses the loop and blocks until the reviewer resolves it in the UI. It's not really a "tool" in the same sense as the others — it's the mechanism by which the agent hands control back.

**Deterministic or LLM.** Neither. It's a synchronization primitive.

**Latency.** Bounded by human speed.

**Errors.** Reviewer skips (loop resumes with skip noted) or reviewer terminates the run.

**Implementation note (Django, Option 1).** The tool (`await_human_resolution(run_id, doc_id, reason)`) writes a pending-review row, then blocks by polling that row on a short sleep until a `POST /runs/{run_id}/resolve` writes the resolution. No `asyncio.Event`, no ASGI — this runs inside the synchronous streaming generator under `runserver` (WSGI), and the resolving POST is served on another worker thread. The pending review is persisted before the block, so a crash mid-wait can be recovered from (the pausable-resumable requirement holds).

### Example flows through the tools

Three illustrative flows through a batch to make the tool interactions concrete. Useful for diagramming. Not exhaustive — the LLM decides what to call and can vary — but representative of typical patterns, retopic'd to Topic 204 (document destruction & retention).

**Flow 1: A clearly relevant, non-privileged document. (Phase 2, per-document review.)**

Starting condition: the batch queue was populated earlier by phase-1 search calls. Orchestrator picks the next document from the queue (a message discussing deleting old trading records). Calls `read_document`. Sees an internal business discussion about clearing out old files, no lawyers on the participant list, no forward markers in the body. Skips `check_privilege_signals`. Calls `classify_relevance(doc_id)` (the loop injects the run criterion) — returns `{relevant: true, confidence: 0.9, reasoning: "explicit discussion of deleting records..."}`. Proposes decision (relevance: yes, privilege: none). Moves to next document.

Cost per document: two LLM calls (orchestrator turn + classifier). Fast and cheap. This is the modal flow — most documents look like this.

**Flow 2: A document with privilege signals. (Phase 2.)**

Orchestrator picks a message that reads like a litigation-hold instruction. Calls `read_document`. Reads the body, sees "please preserve all documents relating to…" and an "attorney-client privileged" marker. Calls `check_privilege_signals` — tool returns strong content signals (`has_confidentiality_marker: true`, `has_legal_advice_language: true`), and, if the `From:` is present and matches the lawyer list (by email, CN code, or display name), populates `known_lawyers_in_from`. If `From:` was absent, `participants_unresolved: true` and the decision leans on the content signals. Calls `classify_relevance` — returns relevant (a preservation instruction is squarely on-topic for 204). Proposes decision: relevant, privileged.

Cost: orchestrator + deterministic privilege check + classifier.

**Flow 3: A genuinely ambiguous case → human review handoff. (Phase 2.)**

Orchestrator picks a message discussing the company's standard email-retention *schedule* (auto-delete after N days), forwarded among IT and business staff, with a lawyer possibly cc'd but `To:`/`Cc:` partially missing. `read_document` shows the setup; `check_privilege_signals` returns weak/`participants_unresolved`. The orchestrator has genuinely low confidence: is this ordinary records-lifecycle administration (not responsive to 204's evidence/litigation framing), or is it retention policy being discussed *because* of an investigation (responsive)? Rather than guess, it calls `request_human_review(doc_id, "Routine retention-schedule discussion vs. litigation-driven retention — responsiveness turns on context the header doesn't make explicit")`.

Loop pauses. Reviewer sees the document, enters a decision plus rationale. Loop resumes with the resolution appended; the correction joins the corrections list so subsequent similar cases benefit.

**Flow 4: A forwarded document. (Phase 2.)**

Orchestrator picks a message whose body opens with `-----Original Message-----` — an inline forwarded chain (the reliable forward signal here, since there is no threading header). Reading the body, the orchestrator sees an original preservation notice from counsel that has been forwarded onward to a business team. It weighs whether forwarding to non-lawyers affects the privilege posture, using the inline content directly. Classifies as relevant; privilege proposed conservatively. If confidence falls below 0.6, the backend converts the proposal to a `request_human_review` regardless.

**What these flows illustrate.**

- `search_documents` is called at the start of a batch (phase 1), rarely during phase 2.
- `read_document` is called on every document in phase 2.
- `check_privilege_signals` is called when content hints (or, when present, participant metadata) suggest privilege — not always.
- `classify_relevance` is called once per document in phase 2.
- `request_human_review` is called on genuine ambiguity, or is auto-inserted by the backend on low confidence.

The typical document consumes 2–4 LLM calls total. A 25-doc batch is 50–100 LLM calls plus a handful of phase-1 searches.

---

## 4. User interaction design

### Cockpit layout

Four regions, laid out as a grid. Sketch this as a 2×2 with one region wider than the others.

**Top left: Queue panel.** The prioritised list of documents the agent will work through in the current batch. Each row shows: doc ID, subject (or "(no subject)" when absent), sender (or "(unknown sender)" when absent), date, current status (pending, in-progress, awaiting review, decided). The document the agent is currently on is highlighted. Status changes update live via SSE.

**Top right (wide): Active document panel.** The document the agent is currently working on, or the one the reviewer has clicked to inspect. Shows subject, participants, date, body. Below the body, the agent's proposed decision (relevance, privilege, issue tags) with confidence scores and a "reasoning" expandable that shows the classification tool's rationale. Below that, action buttons: Approve, Correct. Because participant and subject fields are often missing in this corpus, the panel must render gracefully with those blank rather than looking broken. **Participants render the resolved `*_display[i].display` label** (canonical name from `documents.participants`) with `"(Unresolved)"` shown greyed-out for `x500_blank`/`other` units; raw X.500 DNs and IMCEAEX proxy addresses are never surfaced to the reviewer. The Queue panel similarly uses `from_display.display` for the sender column, falling back to `"(unknown sender)"` when the field is null.

**Bottom left: Agent reasoning stream.** A live log of what the agent is doing right now. Each entry is one iteration: what tool it called, with what arguments, and (once the result comes back) a one-line summary of the result. Auto-scrolls, but with a "pause auto-scroll" toggle so the reviewer can inspect history. This is the "visibility" mechanism made tangible.

**Bottom right: Audit timeline.** A plain, filterable list of all decisions and corrections in the run. Filterable by document, by decision type, by reviewer vs agent origin. Every entry links to the document and the reasoning that produced it. This is the "reversibility" mechanism. (The query-language bar and permalinks were cut in revision 3 — a plain filterable list only.)

### How each human-in-loop mechanism is realised

**Visibility.** The agent reasoning stream shows every tool call and result in near-real-time. Not "thinking…" — literal tool calls with arguments. When the agent calls `search_documents("shredding retention", ...)`, the reviewer sees that string. When it reads a document, the reviewer sees which document. This is the biggest single differentiator from commercial TAR tools and should feel intentional, not a debug console — style the stream carefully.

**Approval gates.** At the end of every batch (default 25 documents, 5 during dev), and at every explicit `request_human_review` handoff, the loop halts. At batch end, the active document panel switches to a batch summary: N documents proposed for decision, breakdown by relevance/privilege, list of any documents flagged for individual review. Reviewer actions available: "Review individually" (walk through each proposed decision with the option to correct), "Approve all" (commit all proposed decisions as-is), or "Pause run" (halt without committing anything, resume later). Discard-batch was cut — its function is served by reviewing individually and correcting the wrong ones. At a `request_human_review` handoff, the panel shows the single ambiguous document with the reason and the reviewer resolves it inline before the loop resumes.

**Intervention.** During an active batch the reviewer can inspect any document read-only, and can pause the loop entirely. Corrections happen at batch boundaries and at explicit handoffs — not mid-batch. This is a deliberate simplification (see stop conditions in section 2). Once the batch ends or the agent hands off, the correction flow via `POST /corrections` applies: correction is written, summarised into a natural-language note, and injected into the next orchestrator iteration's system prompt. The reasoning stream visibly emits a `correction_applied` event when this happens, so the reviewer sees the correction land before the next document is processed.

**Constraints.** No decision is committed to the production output until the reviewer approves it. The agent's decisions are held with `committed=0` in the decisions table until the reviewer flips them via the API. There is no endpoint that lets the agent commit directly. This is enforced at the schema and API layer, not just by UI convention.

**Reversibility.** The audit timeline is a navigable feature. Every entry has: timestamp, actor (agent or reviewer name), action, target (document, decision, correction), and rationale. Clicking an entry navigates to the document and shows the state at that point in time. Committed decisions can be reversed by opening the entry and clicking "Reverse this decision" — this writes a new decision row with the corrected values and sets `superseded_by` on the old row. Old rows are never deleted. Reversibility is scoped to single-decision reversal, and single-decision reversal is itself a **stretch item** (revision 3) — first to cut if the schedule tightens, in which case the timeline is read-only. There is no bulk-select or full-run rollback.

**Corrections viewer.** A separate panel (or modal from the audit timeline) exposes the exact text currently in the "recent corrections" section of the agent's system prompt (the `corrections.summary` values), with timestamps and links to the documents each originated from. This answers the question "what does the agent currently believe you've told it?" — critical for defensibility and directly demonstrable in the demo.

### Streaming protocol

**Choice: SSE, not WebSockets.** Reasoning: the traffic is entirely one-directional (backend → frontend), SSE is simple to implement in Django via `StreamingHttpResponse` and consume in the browser via `EventSource`, it handles reconnection automatically, and it works over plain HTTP without an upgrade dance. The only case for WebSockets is bidirectional streaming, which we don't need — reviewer actions go over normal `POST` endpoints. Half a day saved.

**Endpoint.** `GET /runs/{run_id}/stream` returns a `text/event-stream` `StreamingHttpResponse`. The view's generator runs the agent loop and `yield`s each event as an SSE frame (`data: {json}\n\n`). Events are JSON payloads with a `type` field.

**Reviewer-action endpoints (HTTP POST).**

- `POST /runs` — create a run, return `run_id`.
- `POST /corrections` — write a correction, generate its summary, queue it for injection.
- `POST /runs/{run_id}/resolve` — resolve a pending human-review handoff (unblocks the polling loop).
- `POST /decisions/{decision_id}/commit` — flip `committed` 0→1 (reviewer-gated; the only path to commit).

**CSRF / CORS.** These POSTs are cross-origin (Vite `:5173` → Django `:8000`). CORS is handled by `django-cors-headers` (already configured for the Vite origin). Because there is no auth in the demo, the API views are `csrf_exempt` (equivalently, DRF is configured without SessionAuthentication) — otherwise the unsafe-method POSTs return 403. One-time setup; note it so it isn't rediscovered mid-build.

**Event types.**

- `run_started` — `{run_id, topic, batch_size}`
- `step_started` — `{step_id, tool, arguments}` sent when a tool call begins
- `step_completed` — `{step_id, result_summary}` sent when the tool returns
- `document_decision_proposed` — `{doc_id, relevance, privilege, issue_tags, confidence}` when the agent proposes a decision
- `human_review_requested` — `{doc_id, reason}` when the agent hands off
- `correction_applied` — `{correction_id, summary}` when a reviewer correction is folded into the context
- `batch_complete` — `{batch_summary}` when a batch finishes
- `run_error` — `{error_type, message}` on failures
- `run_paused` — `{reason}` when the loop halts for any reason

The frontend keeps a `useReducer` state that folds each event into the UI state — queue positions update, active document changes, reasoning stream appends, audit timeline appends. Simple and predictable.

### Audit timeline

A filterable, linkable list — decisions and corrections in one place. Filters like actor (reviewer/agent), type (correction/decision/handoff), and document. Each entry links to the document and the reasoning that produced it. When a judge asks "how did you handle this document?" the reviewer filters by doc ID and gets every event touching that document, in order.

This is the most defensible-feeling part of the demo and worth doing well, but kept deliberately simple: the query-language bar and permalinks were cut in revision 3. A plain filterable list, not a log console.

---

## 5. Data pipeline

### Corpus source

The corpus is the **EDRM Enron Email Data Set v2, de-duplicated text rendering** (`edrmv2txt-v2.tar.bz2`, ~596MB, from the TREC 2010 Legal Track UMD mirror). It is already downloaded and extracted to `data/raw/`. This is the same collection the TREC 2010 Legal Track qrels were assessed against, which is the entire reason we use it: the evaluation answer key aligns to it by construction (see "Evaluation methodology" below).

**This replaces the CMU/CALO maildir entirely.** The original plan ingested CALO and scored against TREC qrels; that is impossible because TREC states no mapping exists between the EDRM collection (which the qrels key to) and the CMU-family collections. See `decisions.md` (2026-07-01).

**`DATA_REFERENCE.md` (repo root) is the authoritative structural description of the extracted corpus**, verified against the actual files. What follows summarises the load-bearing facts; consult that document for the detail and for the explicitly-flagged unverified items.

### On-disk structure (the facts that shape the loader)

- **159 custodian directories** under `data/raw/`, named `edrm-enron-v2_<custodian>_xml.zip/` — these are **plain directories, not zip archives** (the `.zip` suffix and the `_xml` are naming artifacts; the files inside are `.txt`, never XML). Each contains one or more `text_NNN/` subfolders holding the documents.
- **685,592 `.txt` files total** = 455,449 canonical email messages + 230,143 attachments. This matches the published TREC 2010 collection count exactly.
- **Enumeration trap — must glob `*.zip` directories, not `*_xml.zip`.** Enron's two largest custodians (`kaminski-v`, `kean-s`) are split into part-files named `…_xml_1of2.zip`, `…_xml_1of8.zip`, etc. A `*_xml.zip` glob silently skips all 10 of these directories (60,723 files). The ingestion walk must match `*.zip` directories to avoid dropping two whole custodians.
- **Doc-id = filename minus `.txt`** (`3.<num>.<HASH>`), which is exactly the doc-id used in the TREC label files (join verified). **A trailing `.N` suffix = attachment; no suffix = base email.** Every attachment has a matching base (no orphans). **We ingest base emails only** (drop `.N` files) — attachments are on the defer list, and restricting to base emails keeps ingestion and evaluation self-consistent.

### Anatomy of a text file

Each file is: a header block of `Key: value` lines, a blank line, the body, then a fixed ZL Technologies license footer bracketed by `***********` lines, and — for base emails with attachments — a trailing `Attachment: <filename> type=<mimetype>` line after the footer. The loader must **strip the ZL boilerplate footer from the body** before chunking/embedding (it appears on 100% of base emails and would otherwise pollute every embedding).

### Header fields — what you can and cannot rely on

Verified prevalence (sampled; see `DATA_REFERENCE.md` for the per-custodian breakdown, which varies enormously):

- **Always present (100%): `Date:`, `X-SDOC:`, `X-ZLID:`.** `X-SDOC` and `X-ZLID` are ZL's own document identifiers — the only two fields reliable enough to key on unconditionally. Store both.
- **Usually present: `Subject:` (~96%).**
- **Frequently missing: `From:` (~83%), `To:` (~66%), `Cc:` (~11%)** — and dramatically worse for some custodians (e.g. `To:` present on 1/60 sampled `bailey-s` files; `From:`/`To:` on 12/60 `skilling-j`). `Bcc:` was never observed. No `Message-ID:`/`In-Reply-To:`/`References:` ever.
- **Practical rule:** the parser must never assume `From:`/`To:`/`Subject:` exist. Missing participants are stored as null and surfaced honestly through the tools and UI. This is why `check_privilege_signals` carries a `participants_unresolved` flag and leans on content signals (section 3).

### Address formats, the splitter, and resolved units

Participants appear in three coexisting forms: clean SMTP (`name@enron.com` or external), Exchange X.500 DN (`Name </O=ENRON/OU=…/CN=RECIPIENTS/CN=CODE>`), and bare display name with no address. There is **no directory/alias file in the corpus**, and **no `@enron.com` address exists anywhere for an X.500-addressed person** — the `CN=CODE` fragment resolves only to a *display name*. A full survey of the on-disk distribution lives at `docs/participant-format-survey.md`; the load-bearing counts are: `smtp_prefixed` 40.0%, `bare_name` 34.4%, `x500_named` 14.4%, `smtp_external` 7.7%, `smtp_internal` 3.4%, `x500_blank` **1 unit corpus-wide**, `other` 0.03%. `Bcc:` is empty in 455,286 / 455,286 rows (parser hard-codes null).

**Bracket-anchored splitter (`documents/participants.py::resolve_field`, revised 2026-07-04).**
The initial `documents/parsing.py::split_participants` chose a whole-field delimiter based
on whether `</O=` was in the value: `>,` split if it was, plain comma split if not. The
survey proved this mis-split ~1,580 documents at minimum, and re-splitting the whole
corpus via the new resolver corrected **21,174 To: rows and 2,425 Cc: rows** (14× and 2×
the survey estimate — the survey undercounted the plain-comma trap). The three defects
and their fixes:

1. **Case-sensitive marker missing lowercase `</o=`.** 980 documents used a lowercase `</o=` DN marker only, which the uppercase `X500_MARKER = "</O="` check missed → the field fell through to plain-comma split → 2,313 spurious "Lastname" + "Firstname \<DN\>" split pairs across 973 docs (including the sole `x500_blank` unit corpus-wide). **Fix:** the new splitter is case-insensitive on brackets and doesn't depend on the marker's case at all.
2. **`Last, First <addr>` comma trap.** With no X.500 marker in the field, the plain comma splitter also broke "Sogomonian, Aram \<Aram.Sogomonian@…\>" into two units. 1,352 such pairs across 609 docs. **Fix:** the new splitter anchors on `<...>` (which never contains a real separator) and treats the whole non-email run before the bracket as the display name, so `Last, First <addr>` stays intact.
3. **Bare-comma addresses merged beside an X.500 unit.** Once a value contained any `</O=`, every `>,` became a split point — including after ordinary bracketed SMTP addresses — but plain comma-separated bare addresses stayed merged into one stored unit. **Fix:** the new algorithm walks the value once, peels off complete email tokens off the front of each pre-bracket prefix, and only the trailing non-email run becomes the bracket's display.

The new algorithm has a deliberate, documented **over-grouping bias**: a bracketless `"Last, First"` (either the entire field or one recipient among comma-separated plain names, with no `<...>` anywhere to anchor on) over-splits into `"Last"` + `"First"` bare-name units. `token_subset_match` requires every query token in the target, so a lawyer variant `"Sanders, Richard"` will NOT match a bare `"Sanders"` target — the surname alone is not "safe degradation" for privilege matching. Impact is bounded because Enron in-house counsel almost always appear as X.500 or SMTP (bracketed) rather than bare comma-name, but it should be understood as a real limitation, not a free lunch. Under the current lawyer list, the over-split loses recall on bare-name lawyer signals only.

**Single-participant fields use `resolve_unit`, not `resolve_field`.** `From:` always carries one participant, so the ingest / backfill code calls `resolve_unit(headers.get("From"))` directly. This preserves bare `"Last, First"` sender names as one bare_name unit rather than over-splitting into surname + given-name. The initial backfill missed this and corrupted 6,165 `from_display` values (all `from_addr` bare-comma names — `Stark, Cindy`, `Kaminski, Vince J`, etc. — collapsed to surname-only). Corrected 2026-07-04; re-run of the backfill idempotently repaired all 6,165 rows. The `resolve_field` docstring warns callers.

**Resolved units are stored on `Document`.** Alongside the raw `from_addr` / `to_addrs` / `cc_addrs` (kept for audit), each row carries `from_display` (one JSON unit object, or null) and `to_display` / `cc_display` (JSON arrays of unit objects). Unit shape: `{raw, display, kind, cn_code, email, domain}` — see §3 `read_document`. `raw` is a canonicalised single-unit substring (whitespace normalised), not byte-for-byte verbatim; the pristine `raw_headers` column preserves that.

**CN → display-name registry stays cut** (revision 3 decision reinforced 2026-07-04). The survey's one-unit `x500_blank` count corpus-wide means a corpus-wide registry has effectively no remaining justification: there are no `Name </O=…>` entries whose display-name prefix is missing and needs recovery from a lookup table. The 10-lawyer hand-carry, seeded by `manage.py suggest_lawyer_cn_codes` (mines candidates from resolved x500_named units — read-only, prints for eyeballing), covers all demand. `extract_entities` also stays cut; the new `find_participant_documents` tool (§3) covers the "find people" use case in a way that doesn't require entity extraction.

### Encoding and corrupted files

Files are predominantly ASCII (~95%) / UTF-8 (~3%) with CRLF line endings; no high-byte Latin-1/Windows-1252 content was seen in the sample. **However, ~1.7% of files are binary-corrupted** — raw OLE2/MS-Office bytes (including long runs of NUL) leaked into what are nominally plain-text base-email files, not just into attachment parts. Extrapolated, that is on the order of 1,000+ files. **The loader must detect and skip/quarantine non-text `.txt` files defensively** (e.g. reject files with a high NUL-byte ratio or that fail a UTF-8/ASCII decode) rather than assume every `.txt` is parseable. Log skips; do not crash.

### Ingestion (Django management commands)

Ingestion is now two Django management commands (replacing the standalone `ingest.py`), with shared parsing logic in `documents/parsing.py`:

- **`manage.py ingest_documents`** — walk, parse, and load base emails into the `documents` table.
- **`manage.py embed_documents`** — chunk + embed the loaded bodies into Chroma.

`ingest_documents` logic:

1. Walks `data/raw/edrm-enron-v2_*.zip/text_NNN/*.txt` (matching `.zip` **directories**, capturing all 159 custodians).
2. **Skips attachment files** (any `.N.txt`) — base emails only.
3. **Skips binary-corrupted files** (NUL-heavy / undecodable), logging each.
4. Parses each file: split header block from body at the first blank line; extract available header fields (`Date`, `X-SDOC`, `X-ZLID` always; `Subject`/`From`/`To`/`Cc` when present); strip the ZL boilerplate footer; capture the body; note any `Attachment:` line for metadata (the attachment itself is not ingested).
5. Normalises participants across the three address forms via `documents.participants` — call `resolve_unit(headers.get("From"))` for the single-participant From field, and `resolve_field(headers.get("To"))` / `resolve_field(headers.get("Cc"))` for the multi-participant fields. Store raw `from_addr` / `to_addrs` / `cc_addrs` alongside the structured display units `from_display` (one unit) / `to_display` / `cc_display` (arrays). Custodian is taken from the directory name.
6. Inserts into the `documents` table (see section 6), with `doc_id` = filename stem. TEXT columns that carry structured data (`to_addrs`, `cc_addrs`, `attachment_refs`, `raw_headers`, `*_display`) are `json.dumps`-encoded — see the serialisation note below.
7. (removed) Privilege signals are **not** precomputed at ingestion. `check_privilege_signals`
   computes all signals live at call time (the `privilege_signals` cache was dropped —
   see §3 / §6 / decisions.md 2026-07-03). Ingestion touches no privilege state.

**Serialisation of TEXT-JSON columns.** `to_addrs`, `cc_addrs`, `attachment_refs`,
`raw_headers`, and the three `*_display` columns are declared `TextField` in the model but
carry JSON payloads (§6: "TEXT — JSON"). `parse_document_file` `json.dumps`-encodes these
fields before handing them to Django — assigning a raw Python list/dict to a `TextField`
str()-reprs it (single quotes) and breaks `json.loads` downstream. The regression was
introduced when the docstring claimed "JSONField handles serialisation" while the model
was actually `TextField`; corrected 2026-07-04. Migrating these columns to `JSONField`
proper would be cleaner but is a deferred cleanup — no functional gap while `json.dumps`
is applied consistently.

**Task 7 gap (fresh-clone correctness, tracked in §8-A).** `parse_document_file` still
calls the OLD `split_participants` (not `resolve_field`) and does NOT populate the
`*_display` columns at ingest; `embed_documents` still calls the old
`extract_sender_display` for Chroma's `sender` metadata. Fresh clones therefore leave
`*_display` NULL until the corrective `backfill_participants` command runs; the current
production DB is fully backfilled and correct. Task 7 unifies the splitter and populates
`*_display` at ingest time so a fresh clone reaches the correct end state without needing
the backfill.

`embed_documents` logic:

8. Chunks the body for embedding — chunks of ~500 tokens with 50 token overlap, one email may produce 1–5 chunks.
9. Embeds each chunk with `sentence-transformers/all-MiniLM-L6-v2` and writes to Chroma with metadata (`doc_id`, `chunk_index`, `sender` when available, `custodian`, `date`).

Both commands must be idempotent (safe to re-run) and print a summary: documents ingested, files skipped (attachment / corrupt), chunks embedded, parse failures.

**Corpus-wide state (verified 2026-07-04).** `ingest_documents` under Django has completed the full corpus: **455,286 base-email `Document` rows**, of which **288,822 (63.4%) have non-empty bodies** — the remainder are legitimate header-only records (calendar items, Notes housekeeping, etc.) as previously identified on the dev subset. `embed_documents` has embedded all non-empty-body rows: **288,822 distinct doc_ids → 470,033 chunks in Chroma** (zero-body docs carry no chunks by design). Confirmed by SQLite counts on `documents_document` and `data/chroma/chroma.sqlite3`. The stale dev-subset numbers (41,112 ingested / 28,186 embedded → 61,458 chunks) have been retired.

**Runtime.** The full base-email corpus is ~455K messages; embedding on CPU with `all-MiniLM-L6-v2` is the bottleneck. Expect it to be the longest single step. For development, ingest a subset (all judged Topic-204 docs + 2–3 custodians as haystack) and only run the full corpus once, ahead of evaluation/demo. **Note:** any subset used to sanity-check the evaluation must include documents that appear in the Topic 204 qrels, or there will be nothing to score against.

### What goes in SQLite vs Chroma

SQLite is the source of truth for everything structured: documents, participants, privilege signals, agent state, decisions, corrections, audit events. Chroma is a specialised index over email-chunk embeddings and returns doc_ids; the backend then reads the actual document from SQLite. Chroma is never authoritative — if we lose it we can rebuild from SQLite.

### Embedding choice

`sentence-transformers/all-MiniLM-L6-v2` — 384-dim, tiny model, runs on CPU in reasonable time, no API cost. Not the best embeddings available, but for this use case (semantic search inside a fixed corpus) it's ample. Do not use OpenAI or Voyage embeddings unless we have obvious retrieval quality problems.

**Limitations to acknowledge (future-work framing).** `all-MiniLM-L6-v2` is trained on general web text; it works well on Enron because the corpus is business English. Deployment on a domain-specific corpus (medical, patents, non-English) would benefit from a domain-specific or multilingual model. The limitation is domain fit, not embedding quality per se. Worth stating explicitly in the presentation as a real product concern.

### Evaluation methodology (verified against primary sources)

**Gold standard.** TREC 2010 Legal Track Learning-task judgments:
`qrels.t10legallearn.gz`, 97MB, from `https://trec.nist.gov/data/legal/10/` (mirror:
`https://trec-legal.umiacs.umd.edu/corpora/trec/legal10-results/`). One row per
document per topic (5,484,736 rows total — hence the size). Format (confirmed on
download): join key `topic:docid`, then stratum ∈ {100, 1000, 10000, 1000000} and
rel ∈ {−1 unjudged, 0 judged non-relevant, 1 judged relevant}. Doc-ids are the
on-disk filename stems — the join holds by construction. The judged sample per topic
is ~2,720 documents, each assessed by three law-trained reviewers, majority vote. A
rel value other than 0/1 is treated as unjudged (TREC coded ~1.25% of documents
"broken").

**Verified Topic 204 counts (Day-1 checklist, complete — see §8):**
- Judged base-email pool: **387 relevant + 1,641 non-relevant = 2,028** documents.
- Disk join: **2,028 / 2,028 (100%)** — every judged base-email doc-id resolves in
  the `doc_id → path` index (455,449 entries).
- `seed.csv` (Learning-task seed set), Topic 204 base: **44 relevant + 437
  non-relevant = 481** rows. (The previously cited 1,191 counted attachments; base
  emails only is 481.) Never injected into prompts; used for dev sanity checks and
  demo-document selection only.
- Seed ∩ judged overlap: **47** doc-ids, written to `overlap_excluded.txt`,
  subtracted from Metric 1 by `report_eval.py`.
- **Topic 202 fallback evaluated and dismissed:** 387 judged-relevant base emails is
  far above the ~150 fallback trigger. The 202 pipeline (swap the criteria string) is
  documented as a contingency but is not needed.

**Two metrics, reported separately. Never blended.**

*Metric 1 — classification accuracy (the defensibility number).* Eval mode (§2)
classifies judged Topic-204 base emails and scores against the assessor-panel
majority. Report recall first, then precision and F1, always as "on the Topic 204
assessed gold sample, N documents" — never as a population estimate (the sample is
stratified toward documents 2010-era systems ranked highly; we state that).

  - **Plan A (default):** classify the entire judged base-email pool (2,028 docs).
    Cost estimate at Haiku prices: roughly £5–7. Run a 50-doc pilot first to confirm
    per-doc cost and latency before committing.
  - **Plan B (if budget is tight):** classify ALL judged-relevant docs (387) plus a
    fixed-seed random sample of ~800 judged non-relevant. Recall is then exact (every
    relevant doc evaluated). Precision is reported as a derived estimate:
    precision-in-pool = TP / (TP + FPR × N_nonrel), where FPR comes from the
    non-relevant sample and N_nonrel is the full judged non-relevant count (1,641).
    Disclose the construction on the slide's footnote.
  - **Recall ceiling:** the maximum achievable Metric-1 recall is **~89.7%
    (347/387)**. 40 of the 387 judged-relevant docs are header-only records the TREC
    assessors judged relevant via subject-string collision; with no body, the
    classifier cannot recover them. State this in the results-slide footnote so the
    recall number is read against its true ceiling.
  - **Seed hygiene:** seeds are never placed in prompts; the 47-doc seed∩judged
    overlap is excluded from reported metrics regardless.

*Metric 2 — throughput and scale (the impact number).* Measured docs/hour from the
eval run (concurrency-adjusted) and from the live cockpit loop. The deck's
cost/time-saved projection derives from measured throughput against the ~50
docs/hour human baseline. The full-corpus agentic run is demonstrated live in the
video; its purpose is the scale story and the control story, not a recall claim.

**What we do not claim.** End-to-end recall over the 455K collection. TREC systems
were scored on ranked retrieval of the whole collection (best on Topic 204: 29.8%
recall at the 3% cut; best actual F1 26.0%); our Metric 1 is a per-document
classification agreement rate — a different quantity. The results slide may cite the
TREC numbers as context for the topic's difficulty, but never in a same-axis
comparison. If a judge asks "so what's your recall over the whole corpus?", the
honest answer: "we measured the component that determines it — per-document
classification recall of X% — and the search layer's contribution is future
evaluation work; TREC's own best systems found under a third of the relevant
documents on this topic at a 3% review budget, which is why the human stays in the
loop."

**Training-data contamination caveat.** A known limitation of evaluating any large
model on a public benchmark; on a fresh private corpus the numbers are a lower-bound
argument, since reasoning transfers and memorised judgments don't. Don't dwell in the
video; answer honestly if asked.

**Privilege ground truth exists (defer-list pointer).** The Interactive task's Topic
304 (privilege) message-level qrels are published as small plain-text files
(`qrel_leg_int_2010_msg_post.txt` on the NIST legal10 page). Out of scope for this
build; it is the natural next evaluation and worth one line on the "what's next"
slide: "ground truth for privilege exists; we validated responsiveness first."

**The mapping CSVs in `data/raw`.** `docids-v2.csv.bz2` maps canonical doc-id ↔
SDOC#; `msg-uniqmsg.csv.bz2` / `uniqmsg.csv.bz2` cover duplicates. Use docids-v2 as
an ingestion integrity check (X-SDOC in headers must match) and as the authoritative
canonical doc-id list. Optional, not blocking.

### Topic recommendation

Target **TREC 2010 Learning-task Topic 204**: "All documents or communications that describe, discuss, refer to, report on, or relate to any intentions, plans, efforts, or activities involving the alteration, destruction, retention, lack of retention, deletion, or shredding of documents or other evidence, whether in hard-copy or electronic form."

Reasoning:
- It needs **no finance or accounting knowledge** — a lay judge follows "were people talking about destroying evidence?" instantly. This is the spoliation/obstruction angle at the heart of the actual Enron collapse.
- It has a **healthy gold pool** (~6,362 estimated relevant docs; 387 judged relevant base emails), so precision/recall are stable.
- It keeps **privilege thematically central**: litigation-hold and preservation instructions from counsel are exactly the privileged material a reviewer must protect, so the `check_privilege_signals` story integrates naturally.

Backup: **Topic 202 (FAS 140/125)** — documented but **not needed** (204's judged pool is well above the fallback threshold, per the verified counts above).

### The lawyer list (demo build vs real deployment)

For the demo the lawyer list is hardcoded: a dozen or so Enron in-house counsel plus external counsel domains. **Given the address reality, each lawyer entry must carry all three keys — display-name variants, `CN=` code(s), and any clean email(s)** — because internal participants have no recoverable email address and matching must succeed on any form. Start from the lawyer-custodians (Haedicke, Shackleton, Sager, Sanders, Mann, Taylor, Jones, Nemec, Derrick, Heard), verify names against public sources, and grep the corpus once for each person's CN code and display-name variants. Two hours, not half a day.

**In a real product deployment, this is user-provided.** A legal team knows its own in-house counsel and outside firms — day-one input to any matter. The real product has a matter-setup form (list in-house lawyers by name/email, outside firms by domain, optionally upload a bar directory). This is a strength of the design, not a limitation, and worth stating: the tool respects that the client knows its own privilege universe better than any classifier could infer. The demo compresses matter creation into a preloaded fixture.

---

## 6. State model

SQLite, one database file (`db.sqlite3`, the Django default). Six main tables plus a couple of caches. **The schema below is realised as Django models** (`documents/models.py`, `agent/models.py`) with **migrations as the source of truth**; the tables below specify the intended shape. Enable WAL mode via a `connection_created` signal handler running `PRAGMA journal_mode=WAL;` (or `DATABASES["default"]["OPTIONS"]["init_command"]`) — Django does not enable WAL by default, and the streaming-read + action-POST-write pattern (§2) depends on it.

> **Code-conformance note (revision 4).** The current Django models diverge from this
> shape in four places that must be corrected (see §8 checklist): `agent_steps` is
> missing `error`, `tokens_input`, `tokens_output`; `corrections` is missing
> `summary`; `audit_events.payload` is a 255-char field and must widen to JSON/TEXT;
> and `agent_runs` needs a new `run_type` field. Field-name mismatches
> (`completed_at`↔`finished_at`, `superseded_by`↔`superseder_id`,
> `created_at`↔`corrected_at`) are cosmetic — pick one and align.
>
> **Resolved 2026-07-04.** `documents` gained `from_display`/`to_display`/`cc_display`
> (migration 0002) and `parse_document_file` was corrected to `json.dumps`-encode
> TEXT-JSON columns (`to_addrs`, `cc_addrs`, `attachment_refs`, `raw_headers`) —
> previously it handed raw Python lists to `TextField`, which str()-repr'd them with
> single quotes and broke `json.loads` in `read_document`. The live DB was built by an
> earlier json-dumping version so existing rows are unaffected; the fix protects fresh
> clones.

### `documents`

Immutable after ingestion **except for one-time corrective backfills** (e.g. `backfill_participants` re-derives `*_display` and re-splits `to_addrs`/`cc_addrs` from `raw_headers`). No live UI write path exists. **Base-email documents only** (attachments not ingested).

```
doc_id            TEXT PRIMARY KEY   -- filename stem = TREC canonical doc-id = qrel join key
x_sdoc            TEXT               -- ZL identifier, always present
x_zlid            TEXT               -- ZL identifier, always present
message_id        TEXT               -- essentially always null (no Message-ID in this corpus)
thread_id         TEXT               -- best-effort heuristic id assigned during ingestion (may be self)
subject           TEXT               -- often null
from_addr         TEXT               -- often null; may be SMTP, X.500 DN, or bare display name
to_addrs          TEXT               -- JSON array; often null/empty
cc_addrs          TEXT               -- JSON array; usually null/empty
bcc_addrs         TEXT               -- never populated (Bcc not present in corpus); kept for shape
date              TIMESTAMP          -- always present
body              TEXT               -- ZL boilerplate footer stripped
custodian         TEXT               -- from directory name
attachment_refs   TEXT               -- JSON array of {filename, mimetype} from any Attachment: line
raw_headers       TEXT               -- JSON blob of the parsed header lines, for re-derivation
from_display      TEXT               -- JSON object: one resolved unit {raw, display, kind, cn_code, email, domain}, or null
to_display        TEXT               -- JSON array of resolved units (empty/null when no To)
cc_display        TEXT               -- JSON array of resolved units (empty/null when no Cc)
```

Indexes (via `Meta.indexes` / `db_index=True`): `thread_id`, `date`, `from_addr`, `custodian`.

Read: `read_document`, `find_participant_documents`, evaluation, UI.
Write: only by `ingest_documents` (and eval-mode upserts for judged doc-ids — see §2). One-time corrective backfills (e.g. `backfill_participants`) are allowed.

**Note on nullability:** `subject`, `from_addr`, `to_addrs`, `cc_addrs`, and the `*_display` fields are frequently null by nature of the corpus (see section 5). This is expected, not an ingestion bug. The only unconditionally-reliable fields are `doc_id`, `x_sdoc`, `x_zlid`, `date`, `custodian`, and `body`.

**TextField + `json.dumps` (not JSONField).** The JSON-carrying columns above are declared `TextField` and encoded with `json.dumps` at write time. Migrating to `JSONField` proper is cleaner but deferred — no functional gap while encoding is applied consistently. `read.py::_json_list` / `_json_obj` decode defensively (null / already-a-list / bare string fallback). Prior regression where `parse_document_file` handed raw Python lists to `TextField` (str()-repr with single quotes → broke downstream `json.loads`) was fixed 2026-07-04.

### `privilege_signals` (cache) — DROPPED from build scope (decision 2026-07-03)


Participant-based signals populated during ingestion (against the lawyer list, using SMTP / CN-code / display-name matching); content and context signals computed at call time and merged.

```
doc_id                      TEXT PRIMARY KEY
lawyers_in_from             TEXT   -- JSON array
lawyers_in_to               TEXT   -- JSON array
lawyers_in_cc               TEXT   -- JSON array
external_counsel_domains    TEXT   -- JSON array
participants_unresolved     BOOLEAN-- true when From/To absent or unmatchable
has_confidentiality_marker  BOOLEAN
has_legal_advice_language   BOOLEAN
matched_phrases             TEXT   -- JSON array
```

(decision 2026-07-03)


Not built. `check_privilege_signals` computes participant, content, and context signals
**live at call time** from the `documents` row (a substring scan of one body plus matching a
handful of participants against ~10 lawyers is millisecond-cheap on a single document, so a
precompute has no demo-scale payoff and real dependency cost). No model, no migration, no
ingestion coupling. If the cache is ever wanted for scale, `privilege.py::_compute_signals`
is exactly the logic ingestion would run. See decisions.md 2026-07-03, Decision 3.


### `agent_runs`

One row per review run (live or eval).

```
run_id            TEXT PRIMARY KEY
run_type          TEXT              -- 'live' | 'eval'   (NEW, revision 4)
topic             TEXT
criteria          TEXT
started_at        TIMESTAMP
finished_at       TIMESTAMP
status            TEXT              -- running, paused, completed, errored
batch_size        INTEGER
current_batch_id  TEXT
```

Read: UI, resumption logic. Write: on run start, on status changes. Eval mode creates a row with `run_type='eval'`.

### `agent_steps`

One row per iteration of the loop. This is what enables resumability.

```
step_id           INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT              -- FK to agent_runs
iteration         INTEGER
tool              TEXT
arguments         TEXT              -- JSON
result            TEXT              -- JSON, may be large
started_at        TIMESTAMP
completed_at      TIMESTAMP
error             TEXT              -- null if success   (MISSING in code — add)
tokens_input      INTEGER           -- (MISSING in code — add)
tokens_output     INTEGER           -- (MISSING in code — add)
```

Indexes: `run_id`, composite `(run_id, iteration)`.

Read: transcript reconstruction, audit timeline. Write: at the start and end of every tool call. The token fields back the §2 budget tracking; the error field backs the error-budget stop condition.

### `decisions`

Proposed and committed classifications.

```
decision_id       INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT              -- FK to agent_runs
doc_id            TEXT              -- FK to documents (eval upserts a Document row first)
proposed_at       TIMESTAMP
proposed_by       TEXT              -- 'agent' or 'reviewer'
relevance         BOOLEAN
privilege         TEXT              -- 'privileged', 'not_privileged', 'unclear'
issue_tags        TEXT              -- JSON array
confidence        REAL
reasoning         TEXT
committed         BOOLEAN DEFAULT 0
committed_at      TIMESTAMP
committed_by      TEXT
superseded_by     INTEGER           -- FK to another decision_id if reversed
```

The `committed` flag is the key constraint enforcing the "humans commit" rule. Rows can only flip from `committed=0` to `committed=1` via `POST /decisions/{decision_id}/commit`, which requires a reviewer session. Reversal creates a new decision row with `superseded_by` pointing to the old one — never delete history. Eval-mode rows belong to a `run_type='eval'` run and stay `committed=0` forever.

### `corrections`

```
correction_id     INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT
doc_id            TEXT              -- may be null (general guidance)
field             TEXT              -- 'relevance', 'privilege', 'issue_tag'
original_value    TEXT
corrected_value   TEXT
rationale         TEXT
summary           TEXT              -- natural-language form injected into agent context (MISSING in code — add)
created_at        TIMESTAMP
created_by        TEXT
```

Read: on every orchestrator iteration (recent N corrections for the run). Write: on `POST /corrections`. The `summary` field is load-bearing — it is the exact text the corrections viewer displays and the loop injects; without it the injected text isn't persisted.

### `audit_events`

The union of everything the audit timeline shows.

```
event_id          INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT
timestamp         TIMESTAMP
actor             TEXT              -- 'agent' or reviewer name
event_type        TEXT              -- 'tool_call', 'decision_proposed',
                                    -- 'decision_committed', 'correction',
                                    -- 'human_review_request', 'reversal'
target_doc_id     TEXT              -- may be null
payload           TEXT              -- JSON, event-specific (code has CharField(255) — widen to JSON/TEXT)
```

Written by a lightweight event writer that other write paths call. Indexed on `run_id`, `target_doc_id`, `event_type`, `timestamp`.

### Read/write pattern during one iteration

1. Orchestrator call begins. Read from SQLite: `agent_runs` (current run state), `agent_steps` for the current `run_id` ordered by iteration DESC LIMIT 3 (the transcript window), `corrections` for the current `run_id` ordered by created_at DESC LIMIT 10.
2. LLM responds with a tool call. Write: `agent_steps` row with `started_at` set, `completed_at` null.
3. 3. Tool executes. Reads its specific tables — `documents` for `read_document`; `documents`
   (participants + body) for `check_privilege_signals`, which computes all signals live (no
   cache); Chroma plus a `decisions` filter for `search_documents`.
4. Tool returns. Update the `agent_steps` row with `result`, `completed_at`, tokens.
5. If the tool was `classify_relevance`, additionally write a `decisions` row with `committed=0` and an `audit_events` row.
6. Stream SSE events to frontend after each write (i.e. `yield` from the generator).

### Why SQLite is enough, and where it would break

Enough because: single-writer (the Django process), small total volume (a few hundred MB of state at most), no concurrent users in the demo scenario. WAL mode lets the long-lived stream read concurrently with the short action-POST writes on the multithreaded dev server. Would break at: multiple concurrent reviewers, multi-machine deployment, or real production with millions of decisions. None applies to a hackathon demo. If a judge asks about scaling, the honest answer is Postgres and a job queue; SQLite is a deliberate choice to save a day.

---

## 7. The demo

Submission is GitHub repo + pitch deck + demo/pitch video. There is no live judging
session. Consequences: the screencast is not the backup — it is the deliverable;
multiple takes are allowed; the 90-second script below is the video's spine,
bookended by ~20s of problem framing and ~20s of results. Record with the full corpus
ingested if the overnight run succeeded, otherwise on the largest ingested subset
(and say the actual number on screen — never claim 455K if fewer are indexed).

### The setup (0:00 – 0:10)

Landing slide. Big number in the middle: **~9,000**. Underneath: "reviewer-hours to classify ~455,000 emails at industry norm (~50 docs/hour). Roughly $450,000. About 10 weeks." (Use the exact corpus figure — ~455,449 base-email messages, 685,592 documents including attachments — and derive the hours/cost from your chosen baseline rate; the round numbers here are illustrative.)

Say: "This is what e-discovery looks like today. Every large lawsuit or regulatory investigation runs through weeks of contract attorneys reading email. We built a cockpit where the AI does the reading and the lawyer stays in charge."

### The framing (0:10 – 0:20)

Cut to the cockpit, cold. Topic loaded: "It's 2002. You're investigating Enron. Find every email where employees discussed destroying, deleting, or withholding documents — the evidence-destruction question at the heart of the collapse."

Say: "This is our investigator's screen. The AI is about to work through hundreds of thousands of Enron emails looking for documents about destroying or preserving evidence. Watch it."

Click "Start."

### The agent working (0:20 – 0:50)

Reasoning stream lights up. Agent calls `search_documents("shred destroy documents retention hold preserve")` — the string appears on screen. Results come back. Agent picks a document, calls `read_document`, then (where signals warrant) `check_privilege_signals`, then `classify_relevance`. All of this streams in real-time on the left. On the right, the active document panel shows what the agent is looking at.

Say (over the stream): "You can see every step. It's searching. It's reading this document. It's checking whether anyone on this email is a lawyer — because instructions from counsel to preserve documents are privileged, and we must not hand those over by mistake. It classifies this one as relevant. On to the next."

Let it run through 4–5 documents. Then it hits a document with mixed signals and hands off:

Say: "Now it's stuck — this one's ambiguous. It's asking us."

**Demo-document candidates (verified real Topic 204 content):** the David Duncan / Nancy Temple Andersen shredding email (`3.34550.I0JJT5RRVWSERDQGEHR31D0UW114DZFVB`) and `3.537709.IYGOZICNJNDV1Z35HJJGK5TAOYJKT4N3B` are vivid spoliation documents to feature. Pair with one ambiguous retention-schedule doc for the intervention beat and one privilege-flagged preservation notice.

### The intervention (0:50 – 1:10)

The active document panel shows the ambiguous document with the agent's "reason for human review" — e.g. a discussion of the company's routine email-retention *schedule*, where it's unclear whether this is ordinary records administration or retention being discussed because of the investigation. Reviewer reads it, clicks "Correct," types: "This is the standard auto-delete policy, not litigation-driven — not responsive." Submit.

Reasoning stream shows a `correction_applied` event.

Next document loads. Reasoning trace on that document now reflects the correction: "Given the recent guidance that routine retention-schedule administration is not responsive absent a litigation context, I'm treating this policy email as non-responsive."

Say: "See the reasoning on this document — it's applying what we just told it. That's the whole point. It works with us, not around us."

### The metrics (1:10 – 1:30)

Cut to the results slide. Two panels.

Left panel: **"Scored against TREC Legal Track expert judgments — Topic 204,
assessed gold sample, N documents."** Lead with classification recall: "of the
documents a panel of three law-trained assessors judged relevant, the agent flagged
[X]% for the reviewer." Then precision, honestly. Footnote the recall ceiling: 40 of
the 387 judged-relevant docs are header-only (no body), capping achievable recall at
~89.7%. One contextual line, carefully phrased as context and not comparison: "this
topic was among the hardest in the original TREC 2010 evaluation — the best research
systems recovered under a third of the relevant documents at a 3% review budget."

Right panel: **Projected impact from measured throughput.** [Actual ingested count]
messages; measured agent triage rate of [Y] docs/hour vs the ~50 docs/hour human
baseline; reviewer-hours and cost saved; weeks → days. Every number on this panel is
derived from a measured quantity in the repo.

Say: "On a real evaluation set from the TREC Legal Track, the agent flagged [X]% of
the documents expert assessors marked relevant — and a human approved every single
commit."

---

## 8. Path to completion — progress checklist

Replaces the earlier day-by-day plan. Grouped by area. Status legend:

- **[x] done** — built and verified (or verified standalone, noted where Django re-verification is still owed)
- **[~] partial** — scaffolded / sketched / file exists but incomplete
- **[ ] not started**

The "never cut" spine (carries Technical 35% + Control 20% + Demo 20%, and eval underwrites Impact 30%): the qrels join + eval numbers, the corrections flow + viewer, the batch approval gate, the reasoning stream.

### Stack picks with reasoning (for reference)

- **LLM: Anthropic straight through, no Groq.** Anthropic native tool use; no agent framework (no LangChain/LangGraph/LlamaIndex/CrewAI). The loop is ~100 lines; write it directly. Frameworks hide what's happening — the opposite of a transparency pitch.
- **Model strategy:** Haiku orchestrator in dev, Sonnet orchestrator for the recorded demo; `classify_relevance` on Haiku always. Batch size 5 dev / 25 demo. Config variables from day 1.
- **Backend: Django + Django REST Framework.** Streaming via synchronous `StreamingHttpResponse` under `runserver` (WSGI) — no ASGI server (revision 4, Option 1). `django-cors-headers` for the Vite origin; API views `csrf_exempt` (no auth in demo).
- **Frontend: React + Vite (+ MUI).** No Next.js. SSE via `EventSource`, event folding via `useReducer`.
- **Vector store: Chroma.** **State: SQLite (WAL).** **Deployment: laptop, localhost.**
- **Budget envelope (£10–15 API):** dev iteration ~£2–3 (Haiku, batch 5); eval pilot ~£0.5; full eval Plan A ~£5–7 (Plan B ~£2–3); demo/video ~£1–2. The 50-doc pilot confirms the extrapolation before the big spend. Tier-1 input-tokens-per-minute is the binding eval constraint — concurrency 5, backoff on 429, expect 1–2 hours wall-clock for the full pool. Log tokens per call from the first run.
- **Embedding hardware:** try `device="cuda"` as a pure speedup; if drivers misbehave >20 min, run CPU. Full-corpus embedding is an overnight job either way. SQLite + Chroma together ~5GB.

### Division of labour

Person A (data/eval, full-time): ingestion, qrels, eval mode, metrics, lawyer list.
Person B (loop/UI, ~0.8): agent loop, tools, SSE, cockpit, corrections flow.
Both own the loop conceptually; the spec remains the tie-breaker.

---

### A. Data & ingestion  (Person A — largely done)

- [x] qrels downloaded, format confirmed (`topic:docid stratum rel`), 5,484,736 rows
- [x] Topic 204 counts locked: 387 relevant + 1,641 non-relevant = 2,028 judged base emails
- [x] Disk join verified: 2,028 / 2,028 (100%)
- [x] `doc_id → path` index built (`doc_id_index.json`, 455,449 entries)
- [x] `seed.csv` counted (Topic 204 base: 44 rel + 437 nrel = 481) and overlap computed (47 doc-ids → `overlap_excluded.txt`)
- [x] Topic 202 fallback evaluated and dismissed (387 ≫ 150 trigger)
- [x] Artefacts + `data/raw/README.md` summaries drafted (qrels, seed, judged_204, index, overlap)
- [x] `documents/parsing.py` written (seven deterministic loader rules)
- [x] `ingest_documents` — full-corpus run complete: **455,286 base-email rows** in `documents_document`, of which **288,822 (63.4%) have non-empty bodies**. Idempotent.
- [x] `embed_documents` — full-corpus run complete: **288,822 distinct doc_ids → 470,033 chunks** in Chroma (matches non-empty-body count exactly). Idempotent re-runs verified.
- [x] `documents/participants.py` — bracket-anchored splitter + `resolve_unit` / `resolve_field` / `token_subset_match` / `MATCHABLE_KINDS`. Fixes the three splitter defects the survey identified (case-sensitive `</O=`; `Last, First` comma trap; bare-comma merges beside X.500). See §5.
- [x] `documents/models.py` — `from_display`, `to_display`, `cc_display` (TextField / JSON) added; migration 0002 applied.
- [x] `parse_document_file` — `_json_or_none` fix: TEXT-JSON columns (`to_addrs`, `cc_addrs`, `attachment_refs`, `raw_headers`) now `json.dumps`-encoded, fixing the read.py-breaking regression.
- [x] `backfill_participants` management command — one-time corrective pass over existing rows: re-derives From/To/Cc from `raw_headers` via the new resolver, writes `to_addrs`/`cc_addrs` (JSON) + `from_display`/`to_display`/`cc_display`. Idempotent. First run corrected 21,174 To rows and 2,425 Cc rows. Bug-fix re-run (2026-07-04) additionally repaired 6,165 `from_display` rows where `resolve_field` had over-split bare "Last, First" From: values.
- [x] `docs/participant-format-survey.md` — corpus-wide format census (455,286 rows, 151 custodians, category × field counts, splitter-defect examples, `x500_named` (CN, display) pairs, `bcc` confirmed empty, notable `other` cases).
- [ ] **Task 7 — fresh-clone correctness.** `parse_document_file` still calls the old `split_participants` and does NOT populate `*_display` at ingest; `embed_documents` still calls `extract_sender_display` for Chroma's `sender` metadata. Update parse to use `resolve_unit`/`resolve_field` and populate the three display columns at ingest; update `embed_documents` to derive the Chroma `sender` from the resolver so fresh Chroma builds agree with SQL `from_display.display`. Retire `split_participants` / `extract_sender_display`. Goal: a fresh clone running `ingest_documents` → `embed_documents` reaches the current end state without needing the backfill.
- [ ] Run `manage.py suggest_lawyer_cn_codes`, eyeball the candidates (watch for surname collisions: Tana Jones / Karen Jones; Cook / Moore / Davis), paste confirmed CN codes into `agent/lawyers.py`. Data task, no code change.

### B. Backend — data model / schema  (partly done; corrections owed)

- [x] Django project + apps (`api`, `agent`, `documents`) scaffolded; settings, CORS, DRF wired
- [x] Core models translated from §6 (Document, AgentRun, AgentStep, Decision, Correction, AuditEvent) + migrations applied
- [ ] `AgentStep`: add `error`, `tokens_input`, `tokens_output` (required by §2 token budget + error-budget stop)
- [ ] `Correction`: add `summary` field (drives the corrections viewer — never-cut feature)
- [ ] `AuditEvent.payload`: widen `CharField(255)` → `JSONField`/`TextField`
- [ ] `AgentRun`: add `run_type` (`live`/`eval`)
- [ ] Eval-mode `Document` upsert path (satisfy `Decision.doc_id` FK without full ingestion)
- [ ] Enable WAL via `connection_created` signal (`PRAGMA journal_mode=WAL`)
- [ ] Add `Meta.indexes` (documents: thread_id/date/from_addr/custodian; audit: run_id/target_doc_id/event_type/timestamp)
- [ ] Align cosmetic field names (`finished_at`↔`completed_at`, `superseder_id`↔`superseded_by`, `corrected_*`↔`created_*`)

### C. Backend — agent loop  (skeleton exists)

- [~] Orchestrator loop (`agent/loop.py`) — sketch with placeholders (`{...}` tool schemas, undefined `truncate`/`emit_sse`/`write_agent_step`)
- [ ] Real Anthropic tool-use `TOOLS` schemas (replace `{...}`)
- [ ] `truncate()` — last-3-iteration transcript window (§2 token budget)
- [ ] `write_agent_step` / `update_agent_step` via ORM, capturing `tokens_input`/`tokens_output`/`error`
- [~] Stop conditions — confidence floor + iteration cap sketched; add batch-complete + error-budget (3-strike)
- [~] `finish_batch` handling (sketched)
- [ ] Model + batch-size config (Haiku/Sonnet, 5/25) as config variables (currently hardcoded Haiku)
- [ ] classify_relevance wiring for Decision 1: the LLM-facing schema exposes **only `doc_id`**
      (drop `criteria`); the dispatch injects `AgentRun.criteria` via `run_id`. Currently
      `execute_tool` reads `args["criteria"]`, which will KeyError once the schema omits it.

### D. Backend — tools  (files exist; content partial)

- [x] read_document (tools/read.py) — null-tolerant ORM fetch; returns `from_display`/`to_display`/`cc_display` resolved units alongside raw; tested end-to-end.
- [x] classify_relevance (tools/classify.py) — forced record_judgment tool call,
      Haiku, ~6k truncation, backoff; prompt v1 exists (no longer blocked)
- [x] check_privilege_signals (tools/privilege.py) — structural matching over resolved units (cn_code/email exact = high; display token-subset = low); `_strength` weights high-conf > display-only; `participants_unresolved` = "unless BOTH From & To usable"; `known_lawyers_in_*` shape now `[{name, via, matched}]`. Computed live.
- [x] agent/prompts.py — orchestrator + classification prompt v1 + builders
- [~] Lawyer-list fixture — 10 §5 custodians + 3-key structure scaffolded;
      docstring updated for structural matching; `cn_codes` still empty (fill via `suggest_lawyer_cn_codes`, §8-A).
- [ ] `find_participant_documents` (new §3 tool) — SQLite-backed scoped participant lookup. Primitives live in `documents/participants.py` (`token_subset_match`, `MATCHABLE_KINDS`); need the tool wrapper + review-state filter + LLM-facing schema + dispatch entry in `agent/tools/__init__.py`.
- [~] search_documents — NEXT (Chroma query + review-state filter)
- [~] request_human_review / await_human_resolution — bridges to loop (§C)

### E. Backend ↔ frontend communication (SSE + actions)  (greenfield — `api/views.py` is just `health`)

- [x] CORS configured (`django-cors-headers`, Vite origin)
- [ ] `GET /runs/{run_id}/stream` — `StreamingHttpResponse` generator that runs the loop and `yield`s SSE frames
- [ ] `POST /runs` — create run, return `run_id`
- [ ] `POST /corrections` — write correction + generate `summary` + queue for injection
- [ ] `POST /runs/{run_id}/resolve` — resolve human-review handoff (unblocks the polling loop)
- [ ] `POST /decisions/{decision_id}/commit` — reviewer-gated commit (only path to `committed=1`)
- [ ] Emit all nine SSE event types (§4) from the loop
- [ ] `csrf_exempt` the API views (cross-origin POSTs otherwise 403)

### F. Frontend — cockpit  (scaffold only — health-check page)

- [x] React + Vite + MUI scaffold; backend health check
- [ ] `EventSource` SSE consumer + `useReducer` event folding
- [ ] Queue panel (live status; "(no subject)"/"(unknown sender)" fallbacks)
- [ ] Active document panel (proposed decision, confidence, reasoning expandable, Approve/Correct)
- [ ] Agent reasoning stream (live tool calls + args; pause-auto-scroll)
- [ ] Batch approval gate (batch summary → Approve all / Review individually / Pause)
- [ ] Corrections viewer (literal injected `summary` text, timestamps, doc links)
- [ ] Audit timeline (plain filterable list — query bar/permalinks cut)
- [ ] Graceful rendering around missing subject/sender everywhere
- [ ] Single-decision reversal — **stretch** (first to cut; timeline read-only if dropped)

### G. Evaluation  (Person A — `run_eval.py` is empty)

- [ ] `run_eval.py` — headless: classify judged 204 base emails (Haiku, prompt v1), concurrency 5 + backoff, ~6k-char truncation, resumable, writes `decisions` under a `run_type='eval'` run
- [ ] `report_eval.py` — recall / precision / F1 / confusion → `results.json`; subtract the 47 overlap doc-ids
- [ ] 50-doc pilot — confirm per-doc cost, latency, valid structured output; sanity-check vs a few seed labels
- [ ] Plan A vs Plan B decision from the pilot cost check
- [ ] Record the ~89.7% recall-ceiling footnote for the results slide

### H. Demo prep & submission

- [~] Demo-document selection — candidates identified (`3.34550.I0JJT5…` Duncan/Temple; `3.537709.IYGOZ…`); still need one ambiguous retention-schedule doc + one preservation notice
- [ ] Results-slide numbers from `report_eval.py`; throughput figures (Metric 2)
- [ ] Record video (Sonnet orchestrator, batch 25, full/largest corpus; multiple takes until the correction-propagation beat lands)
- [ ] Deck (problem, solution, cockpit, honest results, impact, what's next: privilege qrels / XML metadata / structured rule memory)
- [ ] Repo README with setup + the eval reproduction command; submission text last

### I. Infra / docs

- [ ] Update `repo-structure.md` (stale — predates the `agent/` and `documents/` apps; `CLAUDE.md` points builders at it)
- [x] `decisions.md`: Django-pivot entry (added 2026-07-03)
- [ ] Consolidate requirements (root vs `backend/` split; add `sentence-transformers` to `backend/requirements.txt`)

### If behind, cut in this order

1. Single-decision reversal (stretch already) — audit list becomes read-only.
2. Batch "review individually" walkthrough → approve-all plus per-doc correct buttons on the batch summary list.
3. Audit timeline → the SSE event log restyled; no separate table view.
4. Plan A eval → Plan B (all-relevant + non-relevant sample).

Never cut: the qrels join + eval numbers, the corrections flow + viewer, the batch approval gate, the reasoning stream.

### Aggressive defer list

Things not to build. All are legitimate future work; none help the demo:

- Multi-topic support (one topic, 204). Multi-reviewer support (single-user demo). Deployment beyond localhost.
- Rule-memory corrections propagation (context injection only). LLM-resummarised corrections at large cap (N=10 fixed).
- Model choice exposed in UI. Bulk-select reversibility or full-run rollback (single-decision only).
- Mid-batch reviewer intervention (corrections at batch boundaries only).
- `extract_entities` tool (cut revision 1, stays cut 2026-07-04 — the "find people" use case is now served by the deterministic `find_participant_documents` tool over resolved display units, not by LLM-driven entity extraction over free body text). `find_thread` tool (cut entirely, revision 3 — inline body markers only).
- Attachment ingestion (base emails only; eval restricted to base-email judgments to match).
- Deriving real `@enron.com` addresses for X.500 participants (display-name / CN-code matching only).
- CN→display-name corpus-wide map (cut revision 3, reinforced 2026-07-04: the participant-format survey found exactly one `x500_blank` unit corpus-wide, so a corpus-wide registry has ~zero remaining use case. Lawyer list hand-carries CN codes; `suggest_lawyer_cn_codes` mines candidates from the resolved units).
- Audit-timeline query language / permalinks (plain filterable list). Pause/resume UI (schema supports resume; no UI). `issue_tags` UI (field kept, not surfaced).
- Undo/redo beyond reversal-via-new-decision. Discard-batch action. Any authentication. Any tool not in section 3.

New defer-list pointers: privilege evaluation against `qrel_leg_int_2010_msg_post` (Topic 304); EDRM XML metadata ingestion for real threading/addresses (~74GB, production path); structured rule memory for corrections.

### Named risks and mitigations

**Topic 204 pool thin/skewed.** Retired — counted Day 1 (387 relevant), fallback dismissed.

**Participant metadata gaps cripple privilege signals.** Designed for — `check_privilege_signals` weights content signals and flags `participants_unresolved`.

**Binary-corrupted `.txt` files crash ingestion.** ~1.7% carry leaked binary; the loader detects and skips NUL-heavy/undecodable files, logging them. Test on a known-bad file (`DATA_REFERENCE.md` §8 names one).

**Enumeration drops the two largest custodians.** Glob `*.zip` directories, not `*_xml.zip` (kaminski-v/kean-s split parts = 60,723 files). Assert 159 custodians.

**Agent loop generates too many tool calls per document.** Log tokens per iteration from day 1. If a single-document classification exceeds 10 iterations, tighten the system prompt.

**Rate limit during evaluation.** Evaluate against the assessed pool / a sample; concurrency 5 + backoff.

**Privilege classification embarrassingly wrong live.** Fine — it makes the human-in-loop point. Conservative (over-flag) stance means the failure mode is "too many flagged" not "privileged missed."

**SSE connection drops during recording.** SSE reconnects natively; it's a recording, so retake.

**Streaming under `runserver` buffers / the human-review poll deadlocks.** New (revision 4). De-risk early: prove `StreamingHttpResponse` streams token-by-token to `EventSource`, and that a `POST /resolve` on one thread unblocks a parked stream generator on another. If `runserver` streaming misbehaves, the fallback is a short-poll SSE (client reconnects and drains buffered events) rather than switching to ASGI mid-build.

**Late disagreement on a tool boundary or loop structure.** This spec is the tie-breaker. Update the spec (and `decisions.md`) first, then the code. Do not argue in code.

### When to stop building

Hard stop building ~20:00 on Day 2. If a feature isn't working by then, it's cut. Every hour after that is worth two of polish and rehearsal — the video, deck, and story carry the judgment. A last-minute feature that half-works actively damages all three. Then, in order: record the video, build the deck, write the README, submission text last.