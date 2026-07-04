# Agent Loop — Overview

Companion to `ediscovery-technical-spec.md` §2 and §3. This document is the tour: what the loop is, what feeds it, what it produces, and when each event happens. Read this before touching `backend/agent/loop.py`.

## What the loop is

`backend/agent/loop.py::run_batch(run_id)` is a **Python generator** that runs one review batch of the agent. Each `yield` produces one SSE-shaped event dict `{"type": ..., "data": {...}}` for the streaming view to forward to the browser.

**Generator, not a thread, not a coroutine.** The loop lives inside the synchronous streaming view under Django's WSGI runserver (§2 revision 4). Every yielded event flushes to the browser immediately; between yields the loop is doing work (calling the LLM, running a tool, writing to SQLite). No `asyncio`, no worker queue.

## Life of a batch

```
run_batch(run_id)
│
├─ Read AgentRun row  (topic, criteria, batch_size)
├─ Read last 10 Correction rows for this run  ─┐
│                                              ├── build orchestrator prompt
├─ Build system prompt (prompts.py)  ──────────┘
│
└─ Loop:  iteration = 1..MAX_ITERATIONS
   │
   ├── Call Anthropic (Haiku dev / Sonnet demo)
   │      with system prompt + last 3 iteration pairs + tools
   │
   ├── Anthropic returns a tool_use block  (or a run_error is yielded)
   │
   ├── Write AgentStep(started_at, tool, arguments)
   ├── yield step_started
   │
   ├── If tool == "finish_batch":   yield batch_complete, return
   ├── If tool == "request_human_review":  yield human_review_requested (before block)
   │
   ├── Execute tool via agent/tools/execute_tool
   ├── Update AgentStep(result, tokens, completed_at)
   ├── yield step_completed
   │
   ├── If tool == "propose_decision":
   │      ├── If confidence >= 0.60:
   │      │      count += 1, yield document_decision_proposed (proposed_by=agent)
   │      └── If confidence <  0.60:      (backend auto-handoff)
   │             yield human_review_requested (origin=confidence_floor)
   │             block on await_human_resolution
   │             write reviewer Decision, mark agent row superseded
   │             count += 1, yield document_decision_proposed (proposed_by=reviewer)
   │
   ├── If tool == "request_human_review" and reviewer gave a decision:
   │      write reviewer Decision, count += 1,
   │      yield document_decision_proposed (proposed_by=reviewer)
   │
   ├── If count >= batch_size:    yield batch_complete, return
   │
   └── Append tool_result to transcript, truncate to last 3 pairs, loop.
```

## Feeds in

| Source | When | How |
|---|---|---|
| `AgentRun.criteria` | Loop start | Injected into orchestrator system prompt AND into every `classify_relevance` call (dispatch reads `AgentRun.criteria` — the LLM never sees it, per decisions.md 2026-07-03 Decision 1) |
| `AgentRun.topic` / `AgentRun.batch_size` | Loop start | Prompt substitution + batch cap |
| `Correction.corrected_value` (last 10 for this run) | Loop start | Reasoning field parsed from packed `rel: 1, priv: 0, reason: "..."` string and injected under `RECENT GUIDANCE FROM THE REVIEWER` (spec §2 corrections propagation) |
| `Document` bodies + resolved participants | Per-iteration (via the tools) | Read by `read_document`, `classify_relevance`, `check_privilege_signals`, `search_documents` |
| `Chroma` chunk embeddings | Per `search_documents` call | Similarity ranking |
| `Decision` rows (any state) for this run | Per `search_documents` call | Review-state filter — excludes already-touched docs |
| Reviewer resolution via `POST /runs/<run_id>/resolve` | On each human handoff | Consumed by `await_human_resolution`'s polling wait |

## Feeds out

| Sink | When | What |
|---|---|---|
| SSE stream (view yields to browser) | Every yield | See event catalog below |
| `AgentStep` row | Per tool call, twice | `_write_step` at start, `_update_step` at end with result / tokens / error |
| `Decision` row (`committed=0`, `proposed_by="agent"`) | Per successful `propose_decision` at/above the floor | The agent's proposal |
| `Decision` row (`committed=0`, `proposed_by="reviewer"`) | On confidence-floor auto-handoff or explicit `request_human_review` with a decision | The reviewer's answer |
| `Decision.superseder_id` (existing row) | On confidence-floor auto-handoff | Links the agent's row to the reviewer's superseding row |
| `HumanReviewRequest` row | On any handoff | Persistent record (created before the poll blocks — resumability, §2) |

The loop does **not** write `AuditEvent` rows. That's the `POST /commit`, `POST /corrections`, and `POST /resolve` endpoints' job. The loop's own audit trail lives in `AgentStep`.

## SSE event catalog

Every yielded event is `{"type": <name>, "data": <payload>}`. Payloads are JSON-serialisable dicts. Frontend folds each into its `useReducer` state.

| Type | When | Payload |
|---|---|---|
| `run_started` | Once, before the first iteration | `{run_id, topic, batch_size}` |
| `step_started` | Before executing a tool | `{step_id, tool, arguments}` |
| `step_completed` | After the tool returns (including errors) | `{step_id, result_summary}` — one-line summary; full result lives in `AgentStep.result` |
| `human_review_requested` | Before blocking on a reviewer, both for LLM-initiated and confidence-floor auto | `{doc_id, reason, origin: "agent"\|"confidence_floor"}` |
| `document_decision_proposed` | After a Decision row is written | `{doc_id, decision_id, relevance, privilege, confidence, proposed_by: "agent"\|"reviewer", ...}` |
| `batch_complete` | Batch cap reached, or LLM called `finish_batch` | `{proposed, reason: "batch_size_reached"\|"llm_finished"}` |
| `run_error` | Any structural failure — LLM API, tool error budget exhausted, malformed streak, handoff failure | `{error_type, message}` |
| `run_paused` | Iteration cap hit (safety net; should never fire) | `{reason: "iteration_cap", proposed}` |

Not yet emitted (belongs to the endpoints, not the loop): `correction_applied` (fires when a `POST /corrections` write happens between batches).

## Stop conditions (§2)

1. **`finish_batch` from the LLM** → `batch_complete` reason `llm_finished`.
2. **Reached `batch_size` proposals** → `batch_complete` reason `batch_size_reached`. Backend-enforced; can hit mid-turn (e.g., after a confidence-floor auto-handoff).
3. **Confidence floor breach on `propose_decision`** → auto-handoff to reviewer. **Does not stop the batch** — the loop continues after the reviewer resolves.
4. **`TOOL_ERROR_BUDGET` (3) errors on the same tool** → `run_error` `tool_error_budget`.
5. **`MALFORMED_STREAK_BUDGET` (3) consecutive LLM turns without a tool call** → `run_error` `malformed_streak`.
6. **`MAX_ITERATIONS` (100)** → `run_paused` `iteration_cap`. Never should fire in normal use.

## Decision write patterns

Three distinct paths, all end with `committed=0` (the reviewer commits via `POST /decisions/<id>/commit`, not built yet):

1. **Agent proposal at/above the floor.** One row, `proposed_by="agent"`.
2. **Agent proposal below the floor → reviewer override.** Two rows:
   - Row A (agent): `proposed_by="agent"`, `superseder_id = Row B.decision_id`
   - Row B (reviewer): `proposed_by="reviewer"`, contains the reviewer's answer
   - Only Row B counts toward `batch_size`. Row A is retained as the audit trail.
3. **LLM explicit `request_human_review` with a reviewer decision.** One row, `proposed_by="reviewer"`. Counts toward `batch_size`.

## Corrections propagation timing

Corrections **only take effect at the start of a batch**. The loop reads the last 10 `Correction.corrected_value` strings for the run, parses out each `reasoning` field (via `api.serializers._VALUE_PATTERN` — the shared packed-string format), and passes them to `prompts.build_orchestrator_system_prompt(recent_corrections=...)`. They land in the `RECENT GUIDANCE FROM THE REVIEWER` block of the system prompt.

**Consequence.** A correction posted mid-batch does NOT influence the current batch's remaining documents (spec §2 note on mid-stream intervention). It influences the *next* batch. Frontend's `bulk_corrections` endpoint (teammate-owned) writes the row; the next `run_batch(run_id)` call picks it up.

The classifier (`classify_relevance`) is **corrections-blind by design** (decisions.md 2026-07-03 Decision 1) — corrections influence the orchestrator's proposal layer, not the underlying classifier prompt.

## Transcript truncation

Anthropic's messages API requires every `tool_use` block to be followed by its matching `tool_result` block in the same messages array. Dropping old messages without care breaks this invariant.

`_truncate(messages, max_pairs=3)` slices at the boundary of the last 3 assistant turns, keeping each turn's following user tool_result intact. Result: the transcript sent to the LLM is at most 6 messages, containing the last 3 tool_use ↔ tool_result pairs plus any inline user nudges.

Older iterations fall out entirely — no summary, no compaction (§2). If the agent starts making stupid mistakes from lack of context, add a summary layer. Not needed at the batch sizes we run.

## Config knobs

All live near the top of `loop.py`:

| Constant | Default | Purpose |
|---|---|---|
| `DEFAULT_MODEL` | `claude-3-5-haiku-latest` (from `AGENT_MODEL` env) | Swap to Sonnet for the recorded demo. `AGENT_MODEL=claude-sonnet-4-5-latest manage.py …` |
| `MAX_OUTPUT_TOKENS` | 2048 | Per orchestrator turn |
| `MAX_ITERATIONS` | 100 | Runaway safety cap |
| `TOOL_ERROR_BUDGET` | 3 | Same-tool consecutive-error halt (§2) |
| `MALFORMED_STREAK_BUDGET` | 3 | Consecutive no-tool-call halt (§2) |
| `CONFIDENCE_FLOOR` | 0.60 | Auto-handoff threshold on `propose_decision.confidence` (§2) |
| `CORRECTIONS_INJECT_N` | 10 | Rolling corrections window (§2) |
| `MAX_TRANSCRIPT_PAIRS` | 3 | Truncation window (§2) |
| `MAX_RETRIES` / `INITIAL_BACKOFF_SECONDS` | 5 / 2.0 | Anthropic rate-limit backoff |

`AgentRun.batch_size` is the per-run batch cap (5 dev, 25 demo per §8). Persisted in the row, not a code constant.

## Tool schemas — a note on the classifier

`classify_relevance`'s LLM-facing tool schema exposes **only `doc_id`**. The criterion is a run constant, injected by the dispatch from `AgentRun.criteria` (decisions.md 2026-07-03 Decision 1). The classifier is the tool that eval mode scores against TREC Topic 204; letting the orchestrator LLM paraphrase the criterion per call would drift the eval baseline.

## What the loop does NOT do

- **Commit decisions.** `Decision.committed=0` on write. The reviewer commits via `POST /decisions/<id>/commit` (not built).
- **Write `AuditEvent` rows.** Endpoints do this on commit / correction / resolve.
- **Emit `correction_applied` SSE.** That fires from the corrections POST handler, not the loop (the loop only reads corrections at start).
- **Resume mid-batch after a crash.** Persistent rows exist (`AgentStep`, `HumanReviewRequest`) but the resume-logic is out of scope for this build. A crashed batch is redone from scratch on the next `run_batch(run_id)` call; already-decided docs are excluded by `search_documents`'s review-state filter, so the next batch naturally skips them.
- **Handle mid-batch reviewer intervention.** Spec §2 explicitly cuts this; corrections only propagate between batches.

## Where it lives

- `backend/agent/loop.py` — the loop itself and TOOLS schemas
- `backend/agent/tools/__init__.py` — dispatch
- `backend/agent/tools/*.py` — one file per tool
- `backend/agent/prompts.py` — orchestrator system prompt + classifier prompt v1
- `backend/agent/models.py` — `AgentRun`, `AgentStep`, `Decision`, `Correction`, `AuditEvent`, `HumanReviewRequest`
- `backend/api/serializers.py` — `_VALUE_PATTERN` (packed correction format the loop reads)

## How the streaming view will use it

Not built yet, but the shape:

```python
# api/views.py (future)
from django.http import StreamingHttpResponse
import json
from agent.loop import run_batch

def run_stream(request, run_id):
    def sse():
        for event in run_batch(run_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
    return StreamingHttpResponse(sse(), content_type="text/event-stream")
```

Everything else is boilerplate (CORS, `csrf_exempt`, `Cache-Control: no-cache`).
