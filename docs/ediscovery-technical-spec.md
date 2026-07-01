# E-Discovery Reviewer Cockpit — Technical Specification

**Purpose.** Build guide for a 3–4 day hackathon submission. Reference document, not a linear read. Section 8 is the plan; sections 1–7 are the material the plan operates over.

**Reader assumptions.** Two technically literate builders, both new to agentic AI (one with minor prior exposure). Python and JavaScript comfort assumed. Familiarity with FastAPI, React, and SQL assumed. No prior LLM tool-use loop experience assumed.

**Timeline.** Effective build window is ~3.5 days with one teammate having limited daily availability. Effective person-days are ~3, not 6. Scope reductions reflected in section 8.

**Amendment note.** This spec was updated after an architecture review conversation. Key revisions: the loop shape is queue-population-then-review (not search-per-document); `extract_entities` cut from the tool set; mid-batch intervention cut; discard-batch action cut; bulk reversibility UI cut; corrections viewer added; dev-vs-demo cost strategy added. Sections 2, 3, 4, 5, 6, 8 all touched.

---

## 1. System overview

The system is five components running together, four of them on the reviewer's laptop for the demo. In order of dependency: a **SQLite database** holds all persistent state; a **Chroma vector index** holds embeddings of email chunks and answers similarity queries; a **FastAPI backend** hosts the agent loop, the tool implementations, and an SSE endpoint that streams events to the browser; a **React frontend** renders the reviewer cockpit and consumes the SSE stream; the **Anthropic API** is called from the backend as the orchestrator LLM and (separately) as the classifier LLM inside two of the tools.

Direction of dependency is one-way in most places. The frontend talks to the backend over HTTP (for actions like starting a run, submitting a correction, committing a decision) and over SSE (for the stream of agent events flowing the other way). The backend reads and writes SQLite directly, reads Chroma directly, and calls the Anthropic API outbound. Chroma and SQLite do not talk to each other; the backend is the only thing that touches both.

Two things are worth noting about what does *not* exist in this architecture. There is no message queue — the agent loop runs synchronously inside a single FastAPI request handler, streaming as it goes. There is no separate worker process for embeddings or ingestion; ingestion is a one-shot script run before the demo, not a live system. Both simplifications are deliberate cost-cutters that we recover from in section 8 if they cause pain.

Deployment shape: everything runs on one laptop during the demo. Backend on `localhost:8000`, frontend on `localhost:5173` via Vite dev server, SQLite file on disk, Chroma persistent directory on disk. We do not deploy to Railway/Render/Vercel. The reasoning is that hosting adds a day of yak-shaving (env vars, build pipelines, cold starts, CORS, WebSocket/SSE proxying quirks on serverless platforms) for a demo that is going to be shown live from a laptop screen anyway. If hosting later becomes desirable — for judges to poke at post-submission — Railway with a Dockerfile is the least painful option, but that is a stretch goal.

A canonical request flow, sketched so it can become a sequence diagram. Reviewer clicks "Start review on Topic 207 (SPE transactions)": the frontend `POST`s to `/runs`, backend inserts a row into `agent_runs`, opens an SSE connection back to the frontend, and enters the agent loop. First iteration: orchestrator LLM is called with the system prompt, the goal, and empty history; it returns a tool call, say `search_documents("special purpose entity Fastow Chewco", filters={})`. Backend executes the tool (Chroma query, returns 20 doc IDs with scores), writes an `agent_step` row, and streams a `step_completed` SSE event to the frontend. Second iteration: orchestrator called again with the prior tool call and result appended to its history; it decides to `read_document(doc_id=42)`; backend fetches from SQLite, writes a step, streams the event. And so on until a stop condition fires (see section 2).

That loop is the product. Everything else — the UI, the schema, the tools — exists to serve it.

---

## 2. Agentic architecture

### The loop

One iteration of the loop is a single call to the orchestrator LLM followed by execution of at most one tool. The orchestrator LLM is given a prompt containing four things: the system prompt (its role, the review goal, the rules of engagement), the current state summary (queue position, remaining budget, recent corrections), the transcript of prior iterations in this run (each iteration = tool call + tool result), and the tool schema. It responds with either a tool call or a special `finish_batch` signal.

The backend parses the response. If it is a tool call, the tool is executed, the result is captured, and the loop proceeds to the next iteration with the tool call and result appended to the transcript. If it is `finish_batch`, the loop exits and the backend waits for the reviewer's next instruction (typically "approve batch" or "start next batch").

Concretely: use Anthropic's native tool use. The tools are declared in the API call, the model returns `tool_use` content blocks, we execute them, and pass `tool_result` blocks back in the next call. Do not build a custom "the model outputs JSON we parse" layer — Anthropic's tool use handles the parsing, retries on malformed calls, and is battle-tested. This is one of the two or three most important stack choices in the build and it saves roughly half a day.

### Two phases within a run

The loop is a single mechanism, but the orchestrator's behaviour naturally divides into two phases per batch. The distinction matters for reasoning about tool call patterns and for cost estimation.

**Phase 1: Queue population.** At the start of a batch, the orchestrator issues one or several `search_documents` calls to build the candidate pool. It may vary the query terms ("special purpose entity Chewco Fastow", "off-balance-sheet LJM", "SPV equity transactions") to broaden coverage, and may apply filters by date range or custodian. The union of results, deduplicated and filtered against already-reviewed documents (see section 3), becomes the batch queue. Typically 3–5 orchestrator turns.

**Phase 2: Per-document review.** The orchestrator picks the next document from the queue, calls `read_document`, calls `check_privilege_signals` and/or `find_thread` as needed based on what it sees, calls `classify_relevance`, proposes a decision, and moves to the next document. `search_documents` is not called during this phase in the normal case. The exception is when the agent reads a document and encounters a new entity, angle, or reference it wants to explore (e.g. finds mention of an SPE it hadn't queried for) — it can issue an additional search that adds to the queue. This should be rare in practice and each such expansion is logged as a distinct event.

The phase distinction is not enforced by the code — the LLM is free to search whenever it wants — but the system prompt should instruct it in this shape, and the observed behaviour should match.

### What lives in the orchestrator's context

Each iteration's orchestrator call includes:

- **System prompt.** Fixed for a run. Contains the role ("you are an e-discovery review agent"), the specific topic and its criteria, the privilege triage stance (conservative, over-inclusive), the batch-size target, and the instruction to stop and call `request_human_review` under specified conditions.
- **Recent corrections.** A rolling list of the last N (start with N=10) corrections the reviewer has made in this run, injected as natural-language notes. This is our corrections-propagation mechanism. Each correction is one or two sentences: "Correction: Rick Buy is not a lawyer but was acting in a legal capacity on the LJM matter — treat communications with him about LJM as potential privilege." See below.
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

### Corrections propagation (context injection)

When the reviewer overrides an agent decision, the frontend sends the correction to `POST /corrections` with the doc ID, the field corrected (relevance, privilege, issue tag), the new value, and a free-text rationale. The backend does two things: writes a `corrections` row, and generates a one-or-two-sentence natural-language summary of the correction using a small LLM call (or a template — start with a template, upgrade to an LLM summary if templates are too rigid). This summary joins the rolling list of recent corrections.

On the next orchestrator iteration, the recent corrections list (last N, default N=10) is inserted into the system prompt under a heading like "Recent guidance from the reviewer — apply these to similar cases." The agent sees them and, empirically, applies them to subsequent similar documents. This is the crude method: token-wasteful, non-deterministic in application, and it degrades once the correction list gets long. It is also two hours of work and demos beautifully because you can watch the correction land and then watch the next document reflect it in the reasoning trace.

**Corrections viewer.** The reviewer must be able to see exactly what corrections are currently in the agent's context. This is a first-class UI feature — either a panel in the cockpit or a modal reachable from the audit timeline. It shows the literal text being injected into the system prompt right now, with timestamps and links back to the documents each correction originated from. This directly answers the question "what does the agent currently believe you've told it?" — a question a judge or an auditor will ask. Small UI feature, high defensibility payoff.

**Future work on the corrections mechanism.** Two distinct improvement paths, both worth mentioning in the presentation.

- *Large cap with LLM resummarisation.* The N=10 cap is a token-cost concession; in real use, reviewers would rightly expect their older corrections to still influence the agent. The upgrade path: allow the correction list to grow to a much larger cap (say 100), and when it reaches the cap, invoke an LLM pass that consolidates similar corrections into merged rules and drops truly stale ones. This keeps the natural-language architecture but removes the "silently forgot your earliest correction" bug.
- *Structured rule memory.* The more architecturally clean approach. Extract structured rules from corrections ("participant X → privilege signal +1", "documents mentioning entity Y in date range Z → high relevance") and apply them deterministically before or alongside the LLM's judgment. More engineering, more principled, better long-term. This is the "what we'd build next" item in the presentation.

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

Combining all four: a dev batch should cost well under $0.50. A full demo/evaluation run under $5. Track token usage per run and log it; the numbers should confirm this. If they don't, the truncation isn't working.

Practical target: keep each orchestrator call under 15K input tokens.

### Failure modes

- **Tool errors** (Chroma unavailable, missing document, malformed input) return an error object to the LLM as the tool result. The LLM sees the error and typically retries with a corrected call. If the same tool fails 3 times, we halt.
- **Malformed tool calls** are handled by Anthropic's SDK — the model can course-correct. If we see 3 malformed calls in a row, halt.
- **LLM refusals** ("I cannot make a legal judgment") are rare with a well-scoped system prompt but possible. Mitigation: the system prompt is explicit that the agent is making a *proposed classification for human review*, not a legal opinion. If a refusal happens, log it, skip the document, and surface it in the audit log.
- **Rate limits.** Anthropic's tier-1 rate limits are generous but not infinite. Real risk during evaluation runs where we might make thousands of calls. Mitigation: exponential backoff on 429s built into every LLM call, and a run-level concurrency cap of 1 (never run two batches simultaneously).

---

## 3. Tool specifications

Seven tools. For each: signature, data source, deterministic vs LLM, latency expectation, error behaviour.

The general design principle: tools should have crisp responsibilities and be independently testable. The LLM's job is orchestration; the tools' job is competent execution of narrow capabilities. Where a tool could plausibly be "the LLM does it inline" versus "we make it a tool," we make it a tool. Two reasons: it isolates the classification logic so we can version and evaluate it separately, and it produces cleaner audit records because every classification is a discrete logged event with structured inputs and outputs.

### `search_documents`

**Signature.** `search_documents(query: str, filters: dict = {}) -> list[SearchHit]` where each hit is `{doc_id, score, snippet, sender, date}`.

**Data source.** Chroma vector index over email chunks. Filters passed to Chroma's `where` clause: `date_range`, `sender_domain`, `custodian`.

**Deterministic or LLM.** Deterministic. Query is embedded with `sentence-transformers/all-MiniLM-L6-v2`, top hits returned. No LLM in the loop for this call.

**Review-state filtering.** Critical. The tool implementation MUST exclude documents that already have a committed decision for the current run, AND documents already in the current batch's queue (proposed but not yet committed). Otherwise the agent will pull the same document into successive batches or into the same batch twice. Implementation: fetch top 50 hits from Chroma, exclude via a SQLite lookup against the `decisions` table filtered by `run_id`, return top 20 of what remains. Both the run and the current batch ID are passed in from the loop context, not by the LLM.

**Latency.** Sub-second on the Enron corpus with a warm Chroma instance, plus a fast SQLite filter step.

**Errors.** Empty results returned as empty list, not an error — this is a valid outcome the LLM should handle (it should try a different query or `finish_batch`). Chroma unavailability returns an error object; the LLM will likely retry with a different query.

**Example call.** `search_documents("Chewco investment special purpose entity", filters={"date_range": ["2001-01-01", "2001-12-31"]})` → list of up to 20 hits, all previously-unreviewed for this run.

### `read_document`

**Signature.** `read_document(doc_id: str) -> Document` where Document is `{doc_id, subject, from, to, cc, bcc, date, body, thread_id, attachments}`.

**Data source.** SQLite `documents` table.

**Deterministic or LLM.** Deterministic. Straight SELECT.

**Latency.** Milliseconds.

**Errors.** Missing doc ID returns an error object. Should never happen if the LLM is calling with IDs from search results.

### `find_thread`

**Signature.** `find_thread(doc_id: str) -> Thread` where Thread is `{thread_id, messages: [Document]}` in chronological order.

**Data source.** SQLite. Threading precomputed during ingestion using message-ID and In-Reply-To headers where present, subject-line normalisation as fallback.

**Deterministic or LLM.** Deterministic.

**Latency.** Milliseconds.

**Errors.** If threading failed for this document (isolated message, no reply chain), returns a Thread containing only the single message. This is not an error state — it's a valid outcome.

**When to call.** The system prompt instructs the orchestrator to call `find_thread` when the current message shows forwarding or reply signals: subject line starts with "FW:", "Fwd:", "Re:", or the body contains "-----Original Message-----" or similar forward markers. These signals mean the visible participants and content in `read_document` are the *current* message's, not the original chain's. A message that reads as an innocuous business forward might originate from a privileged legal discussion; a message that reads as a privileged discussion might have been forwarded to non-lawyers, breaking privilege. Both cases require the thread to detect.

**Why this is a tool and not part of `read_document`.** Threading is expensive to include on every document read (some threads are 50 messages long), and the LLM should call it only when it matters. Making it a separate call is a signal to the model that thread context is worth requesting.

### `extract_entities` — CUT from build scope

Removed after review. Reasoning: in mental simulation of typical flows, the orchestrator rarely calls this tool — participant information and content signals available from `read_document` and `check_privilege_signals` cover most cases where entity awareness would matter. The tool is more useful as a UI display feature ("show people mentioned in this email") than as an agent tool. Cost of building it (spaCy pipeline, cache table, tool wrapper) does not clear the benefit within the timeline. Mention as a future work item if entity-based cross-referencing becomes desirable.

### `check_privilege_signals`

**Signature.** `check_privilege_signals(doc_id: str) -> PrivilegeSignals` where PrivilegeSignals is:

```
{
  participant_signals: {
    known_lawyers_in_from: [str],
    known_lawyers_in_to: [str],
    known_lawyers_in_cc: [str],
    external_counsel_domains: [str]
  },
  content_signals: {
    has_confidentiality_marker: bool,
    has_legal_advice_language: bool,
    matched_phrases: [str]
  },
  context_signals: {
    is_forwarded: bool,
    forwarded_to_non_lawyers: [str],
    thread_length: int
  },
  overall_signal_strength: "none" | "weak" | "moderate" | "strong"
}
```

**Data source.** SQLite (participants, thread), plus a hardcoded list of known Enron in-house counsel names and external counsel domains (Vinson & Elkins @ve.com is the big one). Content regex over the body for phrases like "privileged and confidential," "attorney work product," "seeking legal advice."

**Deterministic or LLM.** Deterministic. Explicitly not LLM-based. Rationale: this tool exists precisely so the privilege triage logic is auditable and defensible. If a judge later asks "why did you flag this as privileged," the answer is a structured signal set, not "the LLM said so." The LLM interprets the signals into a decision, but the signals themselves are produced by transparent rules.

**Latency.** Milliseconds.

**Errors.** None expected; degrades to empty signals on missing metadata.

**The `overall_signal_strength` field** is a simple rules-based aggregate (any lawyer + any content signal = moderate; multiple signals = strong; etc.). It's a hint to the LLM, not a decision.

### `classify_relevance`

**Signature.** `classify_relevance(doc_id: str, criteria: str) -> RelevanceJudgment` where RelevanceJudgment is `{relevant: bool, confidence: float, reasoning: str, key_passages: [str]}`.

**Data source.** SQLite for the document; separate LLM call with a classification-specific prompt.

**Deterministic or LLM.** **LLM-powered.** This is one of the two tools that internally calls the Anthropic API. The classification prompt is fixed and versioned (call it prompt v1, stored as a constant). It takes the document text and the criteria and returns structured output.

**Why this is a tool rather than something the orchestrator does inline.** Three reasons. First, it lets us version the classification prompt independently of the orchestrator prompt. Second, every classification produces a discrete audit record with structured inputs and outputs, which is central to defensibility. Third, it lets us swap the underlying model — we could run the orchestrator on Claude Sonnet and the classifier on Haiku for cost, without changing the loop.

**Latency.** 2–5 seconds per call.

**Errors.** LLM refusal (rare, handled as above), rate limit (backoff), malformed structured output (retry with a stricter prompt, then error).

### `request_human_review`

**Signature.** `request_human_review(doc_id: str, reason: str) -> HumanReviewResult` where HumanReviewResult is `{decision: dict, reviewer_notes: str}`.

**Data source.** This tool pauses the loop and blocks until the reviewer resolves it in the UI. It's not really a "tool" in the same sense as the others — it's the mechanism by which the agent hands control back.

**Deterministic or LLM.** Neither. It's a synchronization primitive.

**Latency.** Bounded by human speed.

**Errors.** Reviewer skips (loop resumes with skip noted) or reviewer terminates the run.

**Implementation note.** The FastAPI request handler awaits an `asyncio.Event` that the frontend sets by `POST`ing the resolution. Straightforward async pattern; the pausable-resumable requirement is satisfied because the pending review is written to the DB before we await, so a crash mid-await can be recovered from.

### Example flows through the tools

Three illustrative flows through a batch to make the tool interactions concrete. Useful for diagramming. Not exhaustive — the LLM decides what to call and can vary — but representative of typical patterns.

**Flow 1: A clearly relevant, non-privileged document. (Phase 2, per-document review.)**

Starting condition: the batch queue was populated earlier by phase-1 search calls. Orchestrator picks the next document from the queue (doc 4472, subject "Re: Chewco unwind proposal"). Calls `read_document(4472)`. Sees an internal Enron finance discussion, no lawyers on the participant list, no forward markers in the subject or body. Skips `find_thread` (no forward signals) and `check_privilege_signals` (no lawyer signals visible). Calls `classify_relevance(4472, criteria)` — returns `{relevant: true, confidence: 0.94, reasoning: "explicit discussion of unwinding Chewco, a named Enron SPE..."}`. Proposes decision (relevance: yes, privilege: none, confidence 0.94). Moves to next document.

Cost per document: two LLM calls (orchestrator turn + classifier). Fast and cheap. This is the modal flow — most documents look like this.

**Flow 2: A document with privilege signals. (Phase 2.)**

Orchestrator picks doc 8891, subject "LJM structure review," from Jordan Mintz (Enron in-house counsel). Calls `read_document(8891)`. Reads the body, sees explicit "attorney-client privileged" marker and legal advice discussion. Calls `check_privilege_signals(8891)` — tool returns `{lawyers_in_from: ["mintz@enron.com"], external_counsel_domains: ["ve.com"], has_confidentiality_marker: true, has_legal_advice_language: true, overall_signal_strength: "strong"}`. Subject line does not indicate forward, body does not contain "-----Original Message-----" — orchestrator skips `find_thread`. Calls `classify_relevance(8891, criteria)` — returns relevant. Proposes decision: relevant, privileged, confidence 0.86.

Cost: three LLM calls (orchestrator + privilege signals is deterministic + classifier), plus deterministic tool calls.

**Flow 3: A genuinely ambiguous case → human review handoff. (Phase 2.)**

Orchestrator picks doc 12030, subject "quick question re structure." From Rick Buy (Enron chief risk officer, not a lawyer) to Andy Fastow, cc'd to Jordan Mintz (counsel). `read_document` shows the setup. `check_privilege_signals` returns `{lawyers_in_cc: ["mintz@enron.com"], has_confidentiality_marker: false, has_legal_advice_language: false, overall_signal_strength: "weak"}`. Weak participant signal, no content signals. Orchestrator has genuinely low confidence — it's unclear whether this is a business discussion with counsel copied for awareness, or a legal advice request routed via the risk officer. Rather than guess with low confidence, it calls `request_human_review(12030, "Lawyer on cc but no explicit request for legal advice — privilege call requires human judgment on business vs legal purpose")`.

Loop pauses. Reviewer sees the document in the active-document panel with the reason. Enters a decision plus a rationale (e.g. "Business discussion, not privileged — Buy is asking Fastow, cc'ing counsel for awareness only"). Loop resumes with the resolution appended to the transcript. The correction also joins the corrections list, so subsequent similar cases benefit.

**Flow 4: A forwarded document. (Phase 2.)**

Orchestrator picks doc 15201, subject "FW: LJM structure review." Calls `read_document` — visible participants are Buy → Fastow, body starts with "-----Original Message-----" and shows a forwarded chain. Because of the forward marker, orchestrator calls `find_thread(15201)` — thread returns 3 messages: an original from Mintz (lawyer) marked "privileged and confidential," a reply from Fastow, and this forward from Buy to Fastow. Calls `check_privilege_signals(15201)` — signals on the current message alone are weak, but the orchestrator now sees from the thread that the original message was privileged. It weighs: privilege was established at the original, but forwarding to Fastow (a business executive) after Mintz's advice may or may not break privilege depending on whether Fastow was in the original privileged circle. Classifies as relevant, privileged, confidence 0.68. Below the confidence floor of 0.6 — proceeds. If the confidence had been below 0.6, the backend would have intercepted and converted to a `request_human_review` regardless of the orchestrator's proposal.

Cost: four LLM calls (orchestrator + classifier + orchestrator turn for the thread inspection).

**What these flows illustrate.**

- `search_documents` is called at the start of a batch (phase 1), rarely during phase 2.
- `read_document` is called on every document in phase 2.
- `check_privilege_signals` is called when participant metadata or content hints suggest privilege — not always.
- `find_thread` is called when forward/reply signals are visible on the current message — not always.
- `classify_relevance` is called once per document in phase 2.
- `request_human_review` is called on genuine ambiguity, or is auto-inserted by the backend on low confidence.

The typical document consumes 2–4 LLM calls total. A 25-doc batch is 50–100 LLM calls plus a handful of phase-1 searches.

---

## 4. User interaction design

### Cockpit layout

Four regions, laid out as a grid. Sketch this as a 2×2 with one region wider than the others.

**Top left: Queue panel.** The prioritised list of documents the agent will work through in the current batch. Each row shows: doc ID, subject, sender, date, current status (pending, in-progress, awaiting review, decided). The document the agent is currently on is highlighted. Status changes update live via SSE.

**Top right (wide): Active document panel.** The document the agent is currently working on, or the one the reviewer has clicked to inspect. Shows subject, participants, date, body. Below the body, the agent's proposed decision (relevance, privilege, issue tags) with confidence scores and a "reasoning" expandable that shows the classification tool's rationale. Below that, three action buttons: Approve, Correct, Request thread context.

**Bottom left: Agent reasoning stream.** A live log of what the agent is doing right now. Each entry is one iteration: what tool it called, with what arguments, and (once the result comes back) a one-line summary of the result. Auto-scrolls, but with a "pause auto-scroll" toggle so the reviewer can inspect history. This is the "visibility" mechanism made tangible.

**Bottom right: Audit timeline.** A queryable log of all decisions and corrections in the run. Filterable by document, by decision type, by reviewer vs agent origin. Every entry links to the document and the reasoning that produced it. This is the "reversibility" mechanism.

### How each human-in-loop mechanism is realised

**Visibility.** The agent reasoning stream shows every tool call and result in near-real-time. Not "thinking…" — literal tool calls with arguments. When the agent calls `search_documents("Chewco", ...)`, the reviewer sees that string. When it reads a document, the reviewer sees which document. This is the biggest single differentiator from commercial TAR tools and should feel intentional, not a debug console — style the stream carefully.

**Approval gates.** At the end of every batch (default 25 documents, 5 during dev), and at every explicit `request_human_review` handoff, the loop halts. At batch end, the active document panel switches to a batch summary: N documents proposed for decision, breakdown by relevance/privilege, list of any documents flagged for individual review. Reviewer actions available: "Review individually" (walk through each proposed decision with the option to correct), "Approve all" (commit all proposed decisions as-is), or "Pause run" (halt without committing anything, resume later). Discard-batch was cut — its function is served by reviewing individually and correcting the wrong ones. At a `request_human_review` handoff, the panel shows the single ambiguous document with the reason and the reviewer resolves it inline before the loop resumes.

**Intervention.** During an active batch the reviewer can inspect any document read-only, and can pause the loop entirely. Corrections happen at batch boundaries and at explicit handoffs — not mid-batch. This is a deliberate simplification (see stop conditions in section 2). Once the batch ends or the agent hands off, the correction flow via `POST /corrections` applies: correction is written, summarised into a natural-language note, and injected into the next orchestrator iteration's system prompt. The reasoning stream visibly emits a `correction_applied` event when this happens, so the reviewer sees the correction land before the next document is processed.

**Constraints.** No decision is committed to the production output until the reviewer approves it. The agent's decisions are held with `committed=0` in the decisions table until the reviewer flips them via the API. There is no endpoint that lets the agent commit directly. This is enforced at the schema and API layer, not just by UI convention.

**Reversibility.** The audit timeline is a navigable feature. Every entry has: timestamp, actor (agent or reviewer name), action, target (document, decision, correction), and rationale. Clicking an entry navigates to the document and shows the state at that point in time. Committed decisions can be reversed by opening the entry and clicking "Reverse this decision" — this writes a new decision row with the corrected values and sets `superseded_by` on the old row. Old rows are never deleted. Reversibility is scoped to single-decision reversal; there is no bulk-select or full-run rollback. If a reviewer realises they've been systematically wrong, they reverse the affected documents one at a time. This is deliberate MVP scope; bulk operations would be a natural feature addition.

**Corrections viewer.** A separate panel (or modal from the audit timeline) exposes the exact text currently in the "recent corrections" section of the agent's system prompt, with timestamps and links to the documents each originated from. This answers the question "what does the agent currently believe you've told it?" — critical for defensibility and directly demonstrable in the demo.

### Streaming protocol

**Choice: SSE, not WebSockets.** Reasoning: the traffic is entirely one-directional (backend → frontend), SSE is simpler to implement in FastAPI and consume in the browser, it handles reconnection automatically, and it works over plain HTTP without upgrade dance. The only case for WebSockets is bidirectional streaming, which we don't need — reviewer actions go over normal `POST` endpoints. Half a day saved.

**Endpoint.** `GET /runs/{run_id}/stream` returns a `text/event-stream` response. Events are JSON payloads with a `type` field.

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

### Audit timeline as a queryable feature

Not just a scrollable list — a filterable, searchable, linkable navigation surface. Query bar supports filters like `actor:reviewer`, `type:correction`, `doc:42`, `date:>2024-01-01`. Each entry has a permalink (URL fragment) that scrolls to and highlights that event. When a judge asks "how did you handle document 42?" the reviewer types `doc:42` and gets every event touching that document, in order.

This is a deliberately overpowered UI for a hackathon, and it's worth the day it takes because it's the most defensible-feeling part of the demo. The "reversibility" story is only credible if the timeline looks like a legal-grade record, not a log console.

---

## 5. Data pipeline

### Corpus source

Use the CMU Enron distribution. Roughly 500K messages, one file per message, folder-per-custodian structure. Downloadable as a tarball. Decompress to a working directory outside the repo — it's ~1.7GB expanded and does not belong in git.

### Parsing

Email parsing is the single most under-estimated part of this build. The Enron corpus is real messy email from 2000–2002 with all the pathologies: mixed encodings (a lot of Windows-1252 mislabeled as ASCII), broken headers, multipart messages with inconsistent MIME, embedded attachments as base64 in the body, quoted-printable soft-line-breaks. Use Python's `email` package with `policy.default` and expect a nontrivial fraction of messages to raise. Wrap parsing in a try/except that logs failures and continues.

Landmines to plan for:

- Encoding. Try UTF-8, fall back to Windows-1252, fall back to Latin-1, replace-on-error as last resort. Do not silently drop non-decodable bytes.
- Sender/recipient parsing. Addresses appear as `"Name" <email@domain>`, `email@domain (Name)`, and mangled variants. Use `email.utils.getaddresses`. Normalise to lowercase email.
- Dates. `email.utils.parsedate_to_datetime` handles most but not all. Fall back to `dateutil.parser`. Some messages have no Date header; use file mtime as a last resort and flag them.
- Threading. Use Message-ID and In-Reply-To where present. For the ~30% of messages missing References/In-Reply-To, fall back to normalised subject line (strip `Re: `, `Fwd:`, trim) plus participant set. Assign each message a `thread_id` (may be its own message-ID if isolated).

### Ingestion script

A single Python script, `ingest.py`, runs once. It:

1. Walks the corpus directory.
2. Parses each message.
3. Inserts into SQLite `documents` (see section 6).
4. Computes participant-based privilege signals against the hardcoded lawyer list, caches in `privilege_signals`.
5. Chunks the body for embedding — chunks of ~500 tokens with 50 token overlap, one email may produce 1–5 chunks.
6. Embeds each chunk with `sentence-transformers/all-MiniLM-L6-v2` (fast, small, good enough).
7. Writes chunk embeddings to Chroma with metadata (doc_id, chunk_index, sender_domain, date).

(No NER step — the `extract_entities` tool was cut. See section 3.)

Expected runtime: 45–90 minutes on a modern laptop for the full 500K corpus. Embedding is the bottleneck. If this is painful during iteration, ingest a 50K subset first for development and only run the full corpus once, the day before submission.

### What goes in SQLite vs Chroma

SQLite is the source of truth for everything structured: documents, participants, threads, entities, privilege signals, agent state, decisions, corrections, audit events. Chroma is a specialised index over email chunk embeddings and returns doc_ids; the backend then reads the actual document from SQLite. Chroma is never authoritative — if we lose it we can rebuild from SQLite.

### Embedding choice

`sentence-transformers/all-MiniLM-L6-v2` — 384-dim, tiny model, runs on CPU in reasonable time, no API cost. Not the best embeddings available, but for this use case (semantic search inside a fixed corpus, not open-domain retrieval) it's ample. Do not use OpenAI or Voyage embeddings unless we have obvious retrieval quality problems — the cost model is much worse and we don't need the quality.

**Limitations to acknowledge (relevant for future work framing).** `all-MiniLM-L6-v2` is trained on general web text. It works well on Enron because the corpus is business English on financial topics — well within the model's training distribution. Deployment on a domain-specific corpus (medical records, technical patents, non-English content) would benefit from a domain-specific or multilingual embedding model. The limitation is not embedding quality per se; it's domain fit. Worth stating explicitly in the presentation as a real product concern rather than a hidden weakness.

### TREC annotation alignment

TREC Legal Track 2010 published relevance judgments (qrels) for 8 topics against the Enron corpus. Each qrel file is a plain text file: `topic_id 0 doc_id relevance_grade`. The `doc_id` in qrels follows a specific format that must match the doc_ids in our ingested corpus.

**This alignment is the thing that most often breaks evaluation** and is worth verifying on day 1, not day 3. Concretely: pick a handful of doc_ids from the qrels, look them up in the ingested SQLite, and verify they are the messages TREC says they are.

**What "normalisation step" means, concretely.** TREC's qrel files identify documents by their own format — usually derived from message file names or paths in the corpus release, sometimes with hashing or zero-padding conventions. When we ingest, we assign our own doc_ids (integer or path-based). If TREC calls a document `enron_data/allen-p/inbox/47.` and we call it `4472`, we can't look up "does TREC think 4472 is relevant." The normalisation step is either (a) assigning our doc_ids to match TREC's format at ingestion, or (b) building a lookup table `{trec_id: our_id}` and using it in the evaluation harness. Option (a) is cleaner. Either takes about 30 minutes once we know the qrel format — hence day 1.

**When we "disagree" with qrels: we don't.** For evaluation purposes, the qrels are the ground truth. If the agent classifies a document as relevant and the qrel says not-relevant, that's a false positive, full stop. This is how IR evaluation has worked for decades and it's not something to argue with in the metrics.

However, TREC qrels are known to be imperfect: human assessors disagree with each other, some qrels are simply wrong, some annotators had incomplete criteria. If during the demo the agent makes a call that seems obviously correct but the qrel disagrees, that's TREC noise rather than a bug in your system. Fine to say calmly if asked: "our precision is 79% on the TREC gold standard; some of the residual is qrel disagreement rather than model error." Don't volunteer this defensively; do note it if pressed.

**Training data contamination — a real methodological caveat.** Anthropic's models were almost certainly trained on the Enron corpus (it's widely published) and quite possibly on the TREC qrels themselves. This is "data contamination" in the eval literature: our recall/precision numbers may be inflated by the model's latent memory of which documents are relevant, not purely by its reasoning about the criteria. This is a known issue with any public-benchmark evaluation of a foundation model — it's not unique to us. Concrete implications:

- Don't dwell on it in the 90-second demo.
- If a judge asks, honest answer: "This is a known limitation of evaluating any large model on a public dataset. On a fresh matter's private corpus the numbers would be a lower bound on capability, since reasoning transfers but memorised judgments don't."
- Do not claim the TREC numbers as clean proof of capability; frame as "shows the tool works on realistic messy input at scale, benchmarked against expert judgments."

Once alignment is confirmed, evaluation is straightforward: for a target topic, retrieve the qrels, run the agent on the corpus (or a sample), compare agent decisions to qrels, compute precision and recall.

### Topic recommendation

Target **TREC 2010 Topic 207** ("all documents referring or relating to any transaction involving a Special Purpose Entity or Vehicle"). Reasoning:

- It maps directly to the SPE fraud demo framing.
- It has a substantial number of relevant documents in the qrels — enough to make precision/recall metrics stable.
- The topic is contentful enough that the agent's reasoning traces are interesting to read live (not just keyword matching).

Backup: **Topic 206** (transactions with Fastow-created entities like Chewco), which is narrower and easier to score well on.

I have not verified the exact 2010 topic numbers from primary sources for this spec — verify against the TREC Legal Track 2010 overview paper on day 1. The final choice depends on qrel volume and topic descriptions. If Topic 207 has too few qrels, fall back to Topic 206 or another SPE-adjacent topic. **Do this verification before writing any evaluation code.**

### The lawyer list (demo build vs real deployment)

For the demo the lawyer list is hardcoded. Content: a dozen or so Enron in-house counsel names (Jordan Mintz, Rex Rogers, Rob Walls, and others documented in the trial record and the Powers Report) plus external counsel domains (`ve.com` for Vinson & Elkins is the primary one, plus a couple of secondary firms). Half an hour of research against public sources. This list drives the participant-based signals in `check_privilege_signals`. The list is not derived from the corpus itself; it is external knowledge we bring in.

**In a real product deployment, this is user-provided.** A legal team knows their own in-house counsel and their outside firms — it is day-one input to any matter setup. The real product would have a matter-setup form: list your in-house lawyers by name and email, list your outside firms and their domains, optionally upload a bar directory for tighter matching. This is a strength of the design rather than a limitation, and worth stating explicitly in the presentation: the tool respects that the client knows their own privilege universe better than any classifier could infer. Commercial e-discovery tools handle it this way for the same reason.

When describing the real-world flow (in the presentation or to judges), the sequence is: matter creation → user uploads corpus and lawyer/counsel list → ingestion runs the participant matching → reviewer starts topic-specific runs. The demo compresses matter creation into a preloaded fixture.

---

## 6. State model

SQLite. One database file, `state.db`. Six main tables plus a couple of caches. Every table has a primary key and the FK relationships noted. Types are SQLite affinities; the actual storage is flexible.

### `documents`

Immutable after ingestion.

```
doc_id            TEXT PRIMARY KEY
message_id        TEXT             -- from email header, may be null
thread_id         TEXT             -- assigned during ingestion, FK-like
subject           TEXT
from_addr         TEXT
to_addrs          TEXT             -- JSON array
cc_addrs          TEXT             -- JSON array
bcc_addrs         TEXT             -- JSON array
date              TIMESTAMP
body              TEXT
custodian         TEXT
raw_headers       TEXT             -- JSON blob for anything else
```

Indexes: `thread_id`, `date`, `from_addr`, `custodian`.

Read: `read_document`, `find_thread`, evaluation, UI.
Write: only by `ingest.py`.

### `privilege_signals` (cache)

Populated during ingestion for the participant-based signals; content and context signals computed at call time and merged. Alternatively, precompute everything.

```
doc_id                      TEXT PRIMARY KEY
lawyers_in_from             TEXT   -- JSON array
lawyers_in_to               TEXT   -- JSON array
lawyers_in_cc               TEXT   -- JSON array
external_counsel_domains    TEXT   -- JSON array
has_confidentiality_marker  BOOLEAN
has_legal_advice_language   BOOLEAN
matched_phrases             TEXT   -- JSON array
```

### `agent_runs`

One row per review run.

```
run_id            TEXT PRIMARY KEY
topic             TEXT
criteria          TEXT
started_at        TIMESTAMP
finished_at       TIMESTAMP
status            TEXT              -- running, paused, completed, errored
batch_size        INTEGER
current_batch_id  TEXT
```

Read: UI, resumption logic.
Write: on run start, on status changes.

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
error             TEXT              -- null if success
tokens_input      INTEGER
tokens_output     INTEGER
```

Indexes: `run_id`, composite `(run_id, iteration)`.

Read: transcript reconstruction, audit timeline.
Write: at the start and end of every tool call.

### `decisions`

Proposed and committed classifications.

```
decision_id       INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT
doc_id            TEXT
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

The `committed` flag is the key constraint enforcing the "humans commit" rule. Rows can only flip from `committed=0` to `committed=1` via a specific API endpoint that requires a reviewer session. Reversal creates a new decision row with `superseded_by` pointing to the old one — never delete history.

### `corrections`

```
correction_id     INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT
doc_id            TEXT              -- may be null (general guidance)
field             TEXT              -- 'relevance', 'privilege', 'issue_tag'
original_value    TEXT
corrected_value   TEXT
rationale         TEXT
summary           TEXT              -- the natural-language form injected into agent context
created_at        TIMESTAMP
created_by        TEXT
```

Read: on every orchestrator iteration (recent N corrections for the run).
Write: on `POST /corrections`.

### `audit_events`

The union of everything the audit timeline shows. Alternatively, this can be a view over the other tables — but a materialised table is simpler to query and index.

```
event_id          INTEGER PRIMARY KEY AUTOINCREMENT
run_id            TEXT
timestamp         TIMESTAMP
actor             TEXT              -- 'agent' or reviewer name
event_type        TEXT              -- 'tool_call', 'decision_proposed',
                                    -- 'decision_committed', 'correction',
                                    -- 'human_review_request', 'reversal'
target_doc_id     TEXT              -- may be null
payload           TEXT              -- JSON, event-specific
```

Written by a lightweight event writer that other write paths call. Indexed on `run_id`, `target_doc_id`, `event_type`, `timestamp`.

### Read/write pattern during one iteration

1. Orchestrator call begins. Read from SQLite: `agent_runs` (current run state), `agent_steps` for the current `run_id` ordered by iteration DESC LIMIT 3 (the transcript window we keep in full — see section 2 truncation rules), `corrections` for the current `run_id` ordered by created_at DESC LIMIT 10.
2. LLM responds with a tool call. Write: `agent_steps` row with `started_at` set, `completed_at` null.
3. Tool executes. Reads its specific tables — `documents` for `read_document` and `find_thread`, `privilege_signals` for `check_privilege_signals`, Chroma plus a `decisions` filter for `search_documents`.
4. Tool returns. Update the `agent_steps` row with `result`, `completed_at`, tokens.
5. If the tool was `classify_relevance`, additionally write a `decisions` row with `committed=0` and an `audit_events` row.
6. Stream SSE events to frontend after each write.

Note: the transcript window here is `agent_steps` (loop iterations within the current run), not `agent_runs` (across-run records). A typo in an earlier draft may have suggested otherwise.

### Why SQLite is enough, and where it would break

Enough because: single-writer (the FastAPI process), small total volume (a few hundred MB of state at most), no concurrent users in demo scenario. Would break at: multiple concurrent reviewers (WAL mode helps but there are limits), multi-machine deployment, or real production with millions of decisions. None of those apply to a hackathon demo. If a judge asks about scaling, the honest answer is Postgres and a job queue; SQLite is a deliberate choice to save a day.

---

## 7. The demo

90 seconds. Non-engineer judge. Rehearse this ten times. What follows is a beat-by-beat script.

### The setup (0:00 – 0:10)

Landing slide. Big number in the middle: **10,000**. Underneath: "reviewer-hours to classify 500,000 documents at industry norm. About $500,000. About 10 weeks."

Say: "This is what e-discovery looks like today. Every large lawsuit or regulatory investigation runs through weeks of contract attorneys reading email. We built a cockpit where the AI does the reading and the lawyer stays in charge."

### The framing (0:10 – 0:20)

Cut to the cockpit, cold. Topic loaded: "It's January 2002. You're an SEC investigator. Find every email about Enron's Special Purpose Entity transactions."

Say: "This is our investigator's screen. The AI is about to work through 500,000 Enron emails looking for SPE-related documents. Watch it."

Click "Start."

### The agent working (0:20 – 0:50)

Reasoning stream lights up. Agent calls `search_documents("special purpose entity Chewco Fastow")` — the string appears on screen. Results come back. Agent picks a document, calls `read_document`, then `check_privilege_signals`, then `classify_relevance`. All of this streams in real-time on the left. On the right, the active document panel shows what the agent is looking at.

Say (over the stream): "You can see every step. It's searching. It's reading document 47. It's checking whether anyone on this email is a lawyer — Vinson & Elkins is Enron's outside counsel, so their address flags. It classifies this one as relevant, high confidence. On to the next."

Let it run through 4–5 documents. Then it hits a document with mixed signals and hands off:

Say: "Now it's stuck — this one's ambiguous. It's asking us."

### The intervention (0:50 – 1:10)

The active document panel now shows the ambiguous document with the agent's "reason for human review." Reviewer reads it, clicks "Correct" on the privilege proposal, types: "Rick Buy was acting as risk officer here, not seeking legal advice — not privileged." Submit.

Reasoning stream shows a `correction_applied` event.

Next document loads. Reasoning trace on that document now mentions the correction: "Given the recent guidance that Rick Buy is not automatically a legal-capacity participant, I'm treating this exchange as non-privileged unless other signals present."

Say: "See the reasoning on this document — it's applying what we just told it. That's the whole point. It works with us, not around us."

### The metrics (1:10 – 1:30)

Cut to a results slide. Two panels.

Left panel: **TREC evaluation on Topic 207**. Recall: 0.87. Precision: 0.79. F1: 0.83. Sample size and topic name.

Right panel: **Projected impact**. 500,000 documents. Agent triage rate: ~2,000 docs/reviewer-hour effective, versus 50 docs/hour baseline. Reviewer-hours: 250 vs 10,000. Cost: $12,500 vs $500,000. Time: 3 days vs 10 weeks.

Say: "On a real evaluation set from the TREC Legal Track, we hit 87% recall and 79% precision. Applied to the full Enron corpus that's a 40x speedup and half a million dollars saved on a single matter. And the lawyer stayed in charge of every commit."

### Backup plans if things break live

**LLM API failure or rate limit.** Have a pre-recorded 30-second screencast of the same workflow queued. Cut to it, narrate over. "This is a recording from earlier — same workflow, same data."

**Agent produces an unfortunate classification live.** Own it, correct it in the UI, and use it to reinforce the point: "This is exactly why the human is in the loop." Judges will remember this favourably.

---

## 8. Path to completion

Opinionated plan. Four days. Two people. One new to agentic AI.

### Stack picks with reasoning

**LLM: Anthropic straight through, no Groq.** The handover doc mentions Groq for dev. Skip it. Reasoning: swapping providers midway costs half a day of adapter code and prompt tuning; Anthropic's tool use is more capable than most alternatives; $5–20 in credits handles the full build if we're careful.

**Model choice within Anthropic — dev vs demo strategy.**

- Orchestrator during development: **Haiku.** ~12x cheaper on input, one-line swap, occasional dumber decisions but loop mechanics identical. Use from day 1.
- Orchestrator during evaluation and demo: **Sonnet.** Better reasoning traces, more reliable classification proposals.
- `classify_relevance` tool: **Haiku always**, including in the demo. The classification prompt is narrow and structured. Halves the per-run LLM cost with negligible quality loss.
- Dev batch size: **5 documents**. Demo batch size: **25**. Config variable from day 1.
- Combined effect: dev batches cost well under $0.50; a full demo/evaluation run under $5.

**Exposing model choice in the UI is cut.** It's a natural feature — "let the reviewer trade cost for quality" — but building it requires either evaluating on multiple models (doubling eval work) or shipping without eval on the alternatives (not credible for a defensibility pitch). Half-day feature that doesn't help the pitch. Add to future work slide.

**Frontend: React with Vite, not Next.js.** Reasoning: Next.js's SSR machinery is friction we don't need for a demo running on localhost. Vite gives us a React dev server in one command with no config. SSE consumption is trivial in either. Half a day saved.

**Backend: FastAPI, as the handover doc suggests.** No serious alternative for a Python-first agent build. Use `async` throughout for the SSE endpoint; the tool implementations can be sync where they're just DB calls.

**Vector store: Chroma.** Between Chroma and LanceDB, Chroma has more examples online, which matters when the submitter is new to this. LanceDB is arguably faster; not enough to matter here.

**State: SQLite with WAL mode enabled.** As specced.

**Agent framework: none.** Do not use LangChain, LangGraph, LlamaIndex, CrewAI, or similar. Anthropic's tool use API is enough. Reasoning: agent frameworks add layers of abstraction that hide what's happening, which is exactly the opposite of what we need for a submission whose central pitch is transparency. Also, they change fast enough that most examples online are stale. The loop in section 2 is roughly 100 lines of Python. Write it directly.

**Deployment: laptop, localhost.** As discussed in section 1.

### Day-by-day plan (3.5 days, one teammate limited)

Effective person-days: ~3. Assume the primary builder handles the loop end-to-end; the second teammate plugs into whichever piece has highest marginal value at each point (tool implementations, UI, ingestion). Do not partition ownership rigidly — the loop is small enough that both need to understand it.

**Day 1: End-to-end thin slice.** Priority is a working loop by end of day, even if the tools are stubs and the UI is ugly. Concretely:

- Morning: ingest a 5K-document subset of Enron. Verify parsing works on the messy real data. Build SQLite schema, populate it. Get Chroma indexed on the subset. **Verify TREC qrel alignment on a handful of doc_ids — do not defer this.**
- Afternoon: build the FastAPI backend with three tools (`search_documents`, `read_document`, `classify_relevance`) — the minimum to demonstrate a loop. Implement the orchestrator loop with Anthropic tool use (Haiku, batch size 5). Run it on a real topic and verify it iterates end-to-end.
- End of day: minimal React frontend showing the reasoning stream over SSE. Ugly, but wired up.

If the loop is not running end-to-end by end of day 1, the plan is in trouble. Fix it before starting day 2.

**Day 2: Remaining tools, real topic, first evaluation numbers.** Priority is being able to run a real evaluation.

- Morning: implement `find_thread`, `check_privilege_signals`, `request_human_review`. The deterministic ones can be built in parallel. Wire in the lawyer/counsel list.
- Afternoon: run the agent on a sample against the target TREC topic (Sonnet + batch size 25 for this evaluation run). Get a first precision/recall number, even if it's bad. Bad numbers now are fine; blind flying to submission day is not.
- End of day: kick off full-corpus ingestion overnight if not already done.

**Day 3: UI, human-in-the-loop mechanisms, corrections flow.** The agent loop should be reliable by now. Turning it into a demo.

- Morning: build the four-region cockpit layout properly. Style the reasoning stream. Build the audit timeline as a simple scrollable filterable list (drop the query-language filter bar — nice but out of scope).
- Afternoon: implement the correction flow and the corrections viewer panel. Verify corrections propagate visibly on the next document. Implement the batch approval gates and the `request_human_review` inline resolution. Test the pause/resume flow.
- End of day: rehearse the demo once. Time it. Identify what breaks.

**Day 4 (morning only, half-day): Polish and metrics.** Hard stop building at **end of morning** (revised from 2pm given tighter timeline), so the afternoon is entirely demo prep.

- Morning: run the final TREC evaluation on the target topic. Fix any last bugs. Prepare the results slide and the setup slide.
- Afternoon: rehearse the demo five times. Record a backup screencast. Write the submission text. Sleep.

**If you fall behind by end of day 2**, cut: the audit timeline goes to a plain list with no filters; the corrections viewer becomes a tooltip rather than a panel; skip `find_thread` (forwards are relatively rare in the corpus and the agent can still classify without it, at some cost to accuracy on forwarded documents). Do **not** cut TREC alignment or the corrections flow — those are the pitch.

### Aggressive defer list

Things not to build. All are legitimate future work; none help the demo:

- Multi-topic support. One topic is enough.
- Multi-reviewer support. Single-user demo.
- Deployment beyond localhost.
- Rule-memory corrections propagation. Context injection only.
- LLM-resummarised corrections at large cap. N=10 fixed.
- Model choice exposed in UI.
- Bulk-select reversibility or full-run rollback. Single-decision reversal only.
- Mid-batch reviewer intervention. Corrections at batch boundaries only.
- `extract_entities` tool. Cut entirely.
- Undo/redo beyond the reversal-via-new-decision pattern.
- Discard-batch action.
- Any authentication.
- Attachment handling. Emails only.
- Entity NER during ingestion.
- Any tool that isn't in section 3.

### Named risks and mitigations

**Risk: TREC alignment fails on day 3.** Mitigation: verify it day 1. If ID mapping is broken, either build a lookup table or fall back to a manual gold standard on a 100-document sample (hand-annotate against the topic).

**Risk: Agent loop generates too many tool calls per document, blowing token budget.** Mitigation: log tokens per iteration from day 1. If a single-document classification takes more than 10 iterations, tighten the system prompt to be more directive. There is a real failure mode where the agent does 30 searches on one document; the system prompt should discourage this explicitly.

**Risk: Rate limit during evaluation run.** Mitigation: run evaluations against a sample (200–500 documents), not the full corpus. Extrapolate. Precision and recall are stable metrics on samples of that size for a topic with reasonable relevance rate.

**Risk: Privilege classification is embarrassingly wrong live.** Mitigation: this is fine and use it to make the human-in-loop point. But also: the conservative stance (over-flag) means the failure mode should be "too many things flagged as privileged" rather than "privileged docs missed." Test this deliberately.

**Risk: SSE connection drops during demo.** Mitigation: SSE has native reconnection. Also: keep the backup screencast ready.

**Risk: Live LLM API outage during demo.** Mitigation: pre-recorded screencast. Do not fight the demo gods.

**Risk: The two of you disagree on the tool boundary for classify_relevance or the loop structure late in the build.** Mitigation: this spec is the tie-breaker. If we've changed our minds, we update this spec first, then the code. Do not argue in code.

### When to stop building

Hard stop at end of morning on day 4 (revised from 2pm given the 3.5-day effective window). If a feature isn't working by then, it's cut. Every hour after that is worth two hours of polish and rehearsal — the demo is 20% of the score and the submission text, video, and story are what carries the judgment. A last-minute feature that half-works actively damages all three.
