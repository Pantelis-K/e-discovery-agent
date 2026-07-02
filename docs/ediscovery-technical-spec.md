# E-Discovery Reviewer Cockpit — Technical Specification

**Purpose.** Build guide for a 3–4 day hackathon submission (UK AI Agent Hackathon EP5, Conduct.ai track). Reference document, not a linear read. Section 8 is the plan; sections 1–7 are the material the plan operates over.

**Reader assumptions.** Two technically literate builders, both new to agentic AI (one with minor prior exposure). Python and JavaScript comfort assumed. Familiarity with FastAPI, React, and SQL assumed. No prior LLM tool-use loop experience assumed.

**Timeline.** Effective build window is ~3.5 days with one teammate having limited daily availability. Effective person-days are ~3, not 6. Scope reductions reflected in section 8.

**Amendment note (revision 1).** This spec was first updated after an architecture review conversation. Key revisions from that pass: the loop shape is queue-population-then-review (not search-per-document); `extract_entities` cut from the tool set; mid-batch intervention cut; discard-batch action cut; bulk reversibility UI cut; corrections viewer added; dev-vs-demo cost strategy added.

**Amendment note (revision 2 — corpus & topic pivot).** This is the current revision. The data source and evaluation topic changed after direct verification against primary TREC sources and against the actual data on disk. Summary of the change, which touches sections 1, 3, 5, 6, 7, 8:

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
  topic 204; drop `.N` attachment ids. (Format inferred from the official evaluation
  toolkit; confirm the columns on download — Day-1, first hour.)
- **`seed.csv` identified**: the TREC 2010 Learning-task seed set. Topic 204 = 59
  relevant + 1,132 non-relevant = 1,191 labelled docs, usable immediately for
  classifier sanity checks and demo-document selection. Never injected into prompts;
  any overlap with the judged eval pool is excluded from reported metrics.
- **Plan recompressed to 2 days** (§8). Submission is repo + deck + recorded video —
  the recording is the deliverable, which removes live-failure risk and moves the
  build hard-stop to mid-evening Day 2.
- Additional cuts: `find_thread` fully cut; audit query bar cut; CN→display-name
  corpus map cut; single-decision reversal demoted to stretch.


See `decisions.md` (entry dated 2026-07-01) for the full context, options considered, and revisit conditions behind this pivot.

---

## 1. System overview

The system is five components running together, four of them on the reviewer's laptop for the demo. In order of dependency: a **SQLite database** holds all persistent state; a **Chroma vector index** holds embeddings of email chunks and answers similarity queries; a **FastAPI backend** hosts the agent loop, the tool implementations, and an SSE endpoint that streams events to the browser; a **React frontend** renders the reviewer cockpit and consumes the SSE stream; the **Anthropic API** is called from the backend as the orchestrator LLM and (separately) as the classifier LLM inside one of the tools.

Direction of dependency is one-way in most places. The frontend talks to the backend over HTTP (for actions like starting a run, submitting a correction, committing a decision) and over SSE (for the stream of agent events flowing the other way). The backend reads and writes SQLite directly, reads Chroma directly, and calls the Anthropic API outbound. Chroma and SQLite do not talk to each other; the backend is the only thing that touches both.

Two things are worth noting about what does *not* exist in this architecture. There is no message queue — the agent loop runs synchronously inside a single FastAPI request handler, streaming as it goes. There is no separate worker process for embeddings or ingestion; ingestion is a one-shot script run before the demo, not a live system. Both simplifications are deliberate cost-cutters that we recover from in section 8 if they cause pain.

Deployment shape: everything runs on one laptop during the demo. Backend on `localhost:8000`, frontend on `localhost:5173` via Vite dev server, SQLite file on disk, Chroma persistent directory on disk. We do not deploy to Railway/Render/Vercel. The reasoning is that hosting adds a day of yak-shaving (env vars, build pipelines, cold starts, CORS, WebSocket/SSE proxying quirks on serverless platforms) for a demo that is going to be shown live from a laptop screen anyway. If hosting later becomes desirable — for judges to poke at post-submission — Railway with a Dockerfile is the least painful option, but that is a stretch goal.

A canonical request flow, sketched so it can become a sequence diagram. Reviewer clicks "Start review on Topic 204 (document destruction & retention)": the frontend `POST`s to `/runs`, backend inserts a row into `agent_runs`, opens an SSE connection back to the frontend, and enters the agent loop. First iteration: orchestrator LLM is called with the system prompt, the goal, and empty history; it returns a tool call, say `search_documents("document retention deletion shredding preserve", filters={})`. Backend executes the tool (Chroma query, returns 20 doc IDs with scores), writes an `agent_step` row, and streams a `step_completed` SSE event to the frontend. Second iteration: orchestrator called again with the prior tool call and result appended to its history; it decides to `read_document(doc_id="3.818908.A0CV...")`; backend fetches from SQLite, writes a step, streams the event. And so on until a stop condition fires (see section 2).

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

**Phase 2: Per-document review.** The orchestrator picks the next document from the queue, calls `read_document`, calls `check_privilege_signals` and/or `find_thread` as needed based on what it sees, calls `classify_relevance`, proposes a decision, and moves to the next document. `search_documents` is not called during this phase in the normal case. The exception is when the agent reads a document and encounters a new angle or reference it wants to explore (e.g. finds mention of a specific records-management project it hadn't queried for) — it can issue an additional search that adds to the queue. This should be rare in practice and each such expansion is logged as a distinct event.

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

### Eval mode (headless)
 
A separate execution path, `run_eval.py`, exists solely to compute the accuracy
metric. It is not the cockpit loop:
 
- **No orchestrator, no Chroma, no human gates.** For each judged Topic-204
  base-email doc-id (from the qrels), read the document text directly (via the
  doc_id→path index built at ingestion; SQLite if already ingested, raw file
  otherwise), call `classify_relevance` (Haiku, prompt v1 — the same versioned
  prompt the cockpit uses), and record the proposed decision.
- **Bypassing the human-commit gate is deliberate and defensible**: eval mode
  measures the classification component; nothing it produces is a "committed"
  decision. Rows are written to `decisions` with a run type of `eval` and
  `committed=0` forever.
- **Resumable**: skips doc-ids that already have an eval decision, so a crash or
  rate-limit stall costs nothing.
- **Concurrency 5 with exponential backoff** (tier-1 input-token limits are the
  binding constraint; expect roughly 25–50 docs/min on Haiku).
- **Body truncation at ~6,000 characters** for cost control (log when truncation
  fires).
- A companion `report_eval.py` computes recall, precision, F1, and the confusion
  counts, and writes `results.json` — the numbers that go on the results slide.
Key property: **eval mode does not depend on full-corpus ingestion or embeddings.**
Only the ~2–3K judged documents need to be readable on disk. The accuracy number
survives even if the overnight embedding run fails.

### Corrections propagation (context injection)

When the reviewer overrides an agent decision, the frontend sends the correction to `POST /corrections` with the doc ID, the field corrected (relevance, privilege, issue tag), the new value, and a free-text rationale. The backend does two things: writes a `corrections` row, and generates a one-or-two-sentence natural-language summary of the correction using a small LLM call (or a template — start with a template, upgrade to an LLM summary if templates are too rigid). This summary joins the rolling list of recent corrections.

On the next orchestrator iteration, the recent corrections list (last N, default N=10) is inserted into the system prompt under a heading like "Recent guidance from the reviewer — apply these to similar cases." The agent sees them and, empirically, applies them to subsequent similar documents. This is the crude method: token-wasteful, non-deterministic in application, and it degrades once the correction list gets long. It is also two hours of work and demos beautifully because you can watch the correction land and then watch the next document reflect it in the reasoning trace.

**Corrections viewer.** The reviewer must be able to see exactly what corrections are currently in the agent's context. This is a first-class UI feature — either a panel in the cockpit or a modal reachable from the audit timeline. It shows the literal text being injected into the system prompt right now, with timestamps and links back to the documents each correction originated from. This directly answers the question "what does the agent currently believe you've told it?" — a question a judge or an auditor will ask. Small UI feature, high defensibility payoff.

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

Combining all four: a dev batch should cost well under $0.50. A full demo/evaluation run under $5. Track token usage per run and log it; the numbers should confirm this. If they don't, the truncation isn't working.

Practical target: keep each orchestrator call under 15K input tokens.

### Failure modes

- **Tool errors** (Chroma unavailable, missing document, malformed input) return an error object to the LLM as the tool result. The LLM sees the error and typically retries with a corrected call. If the same tool fails 3 times, we halt.
- **Malformed tool calls** are handled by Anthropic's SDK — the model can course-correct. If we see 3 malformed calls in a row, halt.
- **LLM refusals** ("I cannot make a legal judgment") are rare with a well-scoped system prompt but possible. Mitigation: the system prompt is explicit that the agent is making a *proposed classification for human review*, not a legal opinion. If a refusal happens, log it, skip the document, and surface it in the audit log.
- **Rate limits.** Anthropic's tier-1 rate limits are generous but not infinite. Real risk during evaluation runs where we might make thousands of calls. Mitigation: exponential backoff on 429s built into every LLM call, and a run-level concurrency cap of 1 (never run two batches simultaneously).

---

## 3. Tool specifications

Six tools. For each: signature, data source, deterministic vs LLM, latency expectation, error behaviour.

The general design principle: tools should have crisp responsibilities and be independently testable. The LLM's job is orchestration; the tools' job is competent execution of narrow capabilities. Where a tool could plausibly be "the LLM does it inline" versus "we make it a tool," we make it a tool. Two reasons: it isolates the classification logic so we can version and evaluate it separately, and it produces cleaner audit records because every classification is a discrete logged event with structured inputs and outputs.

### `search_documents`

**Signature.** `search_documents(query: str, filters: dict = {}) -> list[SearchHit]` where each hit is `{doc_id, score, snippet, sender, date}`.

**Data source.** Chroma vector index over email chunks (base-email documents only — see section 5). Filters passed to Chroma's `where` clause: `date_range`, `sender_domain`, `custodian`.

**Deterministic or LLM.** Deterministic. Query is embedded with `sentence-transformers/all-MiniLM-L6-v2`, top hits returned. No LLM in the loop for this call.

**Review-state filtering.** Critical. The tool implementation MUST exclude documents that already have a committed decision for the current run, AND documents already in the current batch's queue (proposed but not yet committed). Otherwise the agent will pull the same document into successive batches or into the same batch twice. Implementation: fetch top 50 hits from Chroma, exclude via a SQLite lookup against the `decisions` table filtered by `run_id`, return top 20 of what remains. Both the run and the current batch ID are passed in from the loop context, not by the LLM.

**Note on `sender`.** The hit's `sender` field may be null for a meaningful fraction of documents — many records lack a parseable `From:` line (see section 5). Return what is available; the agent and UI must tolerate a missing sender.

**Latency.** Sub-second on the Enron corpus with a warm Chroma instance, plus a fast SQLite filter step.

**Errors.** Empty results returned as empty list, not an error — this is a valid outcome the LLM should handle (it should try a different query or `finish_batch`). Chroma unavailability returns an error object; the LLM will likely retry with a different query.

**Example call.** `search_documents("shred destroy documents retention hold", filters={"date_range": ["2001-09-01", "2002-03-31"]})` → list of up to 20 hits, all previously-unreviewed for this run.

### `read_document`

**Signature.** `read_document(doc_id: str) -> Document` where Document is `{doc_id, subject, from, to, cc, date, body, custodian, attachments}`.

**Data source.** SQLite `documents` table.

**Deterministic or LLM.** Deterministic. Straight SELECT.

**Field-availability reality.** `subject`, `from`, `to`, and `cc` are frequently absent in this corpus and will be returned as null / empty when the source message did not carry them (see section 5 for measured prevalence — `From:` present ~83%, `To:` ~66%, and much lower for some custodians). `date` is always present. The agent's prompt must be told these can be missing so it does not over-interpret a blank `from` as anonymity. `attachments` is always an empty list in the demo build — attachment documents are out of scope (defer list), and we ingest base emails only; the field exists for shape compatibility only.

**Latency.** Milliseconds.

**Errors.** Missing doc ID returns an error object. Should never happen if the LLM is calling with IDs from search results.

### `find_thread` — CUT from build scope (revision 3)

**Signature.** `find_thread(doc_id: str) -> Thread` where Thread is `{thread_id, messages: [Document], confidence: str}` in chronological order.

**Data source.** SQLite. **Important reality (verified on disk):** the EDRM text corpus contains **no `Message-ID`, `In-Reply-To`, or `References` header** — there is no structured field for reconstructing reply/forward chains. Threading is therefore *heuristic and best-effort only*, precomputed during ingestion from normalised subject line + participant overlap + temporal proximity. It is not reliable, and the returned `confidence` field ("high" / "low") must communicate this.

**Deterministic or LLM.** Deterministic (heuristic grouping).

**Latency.** Milliseconds.

**A more reliable forward signal lives in the body.** Roughly 15% of documents contain inline `-----Original Message-----` or `Forwarded by …` blocks in the body text itself. For detecting that a message *is* a forward or reply, and reading the original content, the agent reading the body directly (via `read_document`) is more dependable than `find_thread`. The system prompt should lean on this: treat inline forwarded/quoted body content as the primary evidence of a chain, and `find_thread` as a weak supplement.

**Errors.** If no plausible thread is found, returns a Thread containing only the single message with `confidence: "low"`. This is a valid outcome, not an error.

**Cut candidate.** Because threading is unreliable here and inline body content partly substitutes, `find_thread` is the first tool to cut if the schedule tightens (see section 8). Building it should not block the core loop.

### `extract_entities` — CUT from build scope

Removed in revision 1 and still cut. Reasoning: in mental simulation of typical flows, the orchestrator rarely calls this tool — participant information and content signals available from `read_document` and `check_privilege_signals` cover most cases where entity awareness would matter. The tool is more useful as a UI display feature ("show people mentioned in this email") than as an agent tool. Cost of building it does not clear the benefit within the timeline. Mention as a future work item if entity-based cross-referencing becomes desirable.

### `check_privilege_signals`

**Signature.** `check_privilege_signals(doc_id: str) -> PrivilegeSignals` where PrivilegeSignals is:

```
{
  participant_signals: {
    known_lawyers_in_from: [str],
    known_lawyers_in_to: [str],
    known_lawyers_in_cc: [str],
    external_counsel_domains: [str],
    participants_unresolved: bool     // true when From/To were missing or unmatchable
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

**Data source.** SQLite (participants, body), plus a hardcoded list of known Enron in-house counsel and external counsel domains. Content regex over the body for phrases like "privileged and confidential," "attorney work product," "seeking legal advice," and — relevant to Topic 204 — "litigation hold," "preservation notice," "do not delete."

**Deterministic or LLM.** Deterministic. Explicitly not LLM-based. Rationale: this tool exists precisely so the privilege triage logic is auditable and defensible. If a judge later asks "why did you flag this as privileged," the answer is a structured signal set, not "the LLM said so." The LLM interprets the signals into a decision, but the signals themselves are produced by transparent rules.

**Address-matching reality (verified on disk — this materially changes participant matching).** Internal Enron participants do **not** appear as clean `name@enron.com` addresses. They appear in three inconsistent forms across the corpus: (1) clean SMTP address, (2) Exchange X.500 distinguished name `Name </O=ENRON/OU=…/CN=RECIPIENTS/CN=CODE>`, and (3) bare display name with no address at all. Critically, **no `@enron.com` address exists anywhere in the corpus for an X.500-addressed person** — the `CN=CODE` fragment resolves (via a corpus-wide scan) to a *display name* only, never an email. Consequences for this tool:

- The lawyer list must carry, per lawyer, **all three keys**: display-name variants, `CN=` code(s), and any clean email addresses. Matching succeeds on any one form.
- Because `From:`/`To:` are frequently missing entirely, participant matching has **partial coverage by design**. When participants are absent or unresolvable, set `participants_unresolved: true` and lean on content signals. Do not silently treat "no lawyer found" as "no privilege" — the flag makes the uncertainty explicit to the LLM and the auditor.
- An optional ingestion-time enhancement (see section 5) builds a `CN → display-name` map by scanning the corpus; this improves lawyer matching but is not required for a first pass.

**Latency.** Milliseconds.

**Errors.** None expected; degrades to empty participant signals with `participants_unresolved: true` on missing metadata.

**The `overall_signal_strength` field** is a simple rules-based aggregate (any lawyer + any content signal = moderate; multiple signals = strong; content signals only = weak; etc.). It's a hint to the LLM, not a decision. Given the participant-coverage gaps, content signals are weighted more heavily than the revision-1 design assumed.

### `classify_relevance`

**Signature.** `classify_relevance(doc_id: str, criteria: str) -> RelevanceJudgment` where RelevanceJudgment is `{relevant: bool, confidence: float, reasoning: str, key_passages: [str]}`.

**Data source.** SQLite for the document; separate LLM call with a classification-specific prompt.

**Deterministic or LLM.** **LLM-powered.** This is the one tool that internally calls the Anthropic API. The classification prompt is fixed and versioned (call it prompt v1, stored as a constant). It takes the document text and the criteria and returns structured output. For the demo, `criteria` is the Topic 204 production request: documents relating to the alteration, destruction, retention, lack of retention, deletion, or shredding of documents or other evidence.

**Why this is a tool rather than something the orchestrator does inline.** Three reasons. First, it lets us version the classification prompt independently of the orchestrator prompt. Second, every classification produces a discrete audit record with structured inputs and outputs, which is central to defensibility. Third, it lets us swap the underlying model — we run the orchestrator on Sonnet (demo) and the classifier on Haiku for cost, without changing the loop.

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

Three illustrative flows through a batch to make the tool interactions concrete. Useful for diagramming. Not exhaustive — the LLM decides what to call and can vary — but representative of typical patterns, retopic'd to Topic 204 (document destruction & retention).

**Flow 1: A clearly relevant, non-privileged document. (Phase 2, per-document review.)**

Starting condition: the batch queue was populated earlier by phase-1 search calls. Orchestrator picks the next document from the queue (a message discussing deleting old trading records). Calls `read_document`. Sees an internal business discussion about clearing out old files, no lawyers on the participant list, no forward markers in the body. Skips `find_thread` and `check_privilege_signals`. Calls `classify_relevance(doc_id, criteria)` — returns `{relevant: true, confidence: 0.9, reasoning: "explicit discussion of deleting records..."}`. Proposes decision (relevance: yes, privilege: none). Moves to next document.

Cost per document: two LLM calls (orchestrator turn + classifier). Fast and cheap. This is the modal flow — most documents look like this.

**Flow 2: A document with privilege signals. (Phase 2.)**

Orchestrator picks a message that reads like a litigation-hold instruction. Calls `read_document`. Reads the body, sees "please preserve all documents relating to…" and an "attorney-client privileged" marker. Calls `check_privilege_signals` — tool returns strong content signals (`has_confidentiality_marker: true`, `has_legal_advice_language: true`), and, if the `From:` is present and matches the lawyer list (by email, CN code, or display name), populates `known_lawyers_in_from`. If `From:` was absent, `participants_unresolved: true` and the decision leans on the content signals. Calls `classify_relevance` — returns relevant (a preservation instruction is squarely on-topic for 204). Proposes decision: relevant, privileged.

Cost: orchestrator + deterministic privilege check + classifier.

**Flow 3: A genuinely ambiguous case → human review handoff. (Phase 2.)**

Orchestrator picks a message discussing the company's standard email-retention *schedule* (auto-delete after N days), forwarded among IT and business staff, with a lawyer possibly cc'd but `To:`/`Cc:` partially missing. `read_document` shows the setup; `check_privilege_signals` returns weak/`participants_unresolved`. The orchestrator has genuinely low confidence: is this ordinary records-lifecycle administration (not responsive to 204's evidence/litigation framing), or is it retention policy being discussed *because* of an investigation (responsive)? Rather than guess, it calls `request_human_review(doc_id, "Routine retention-schedule discussion vs. litigation-driven retention — responsiveness turns on context the header doesn't make explicit")`.

Loop pauses. Reviewer sees the document, enters a decision plus rationale. Loop resumes with the resolution appended; the correction joins the corrections list so subsequent similar cases benefit.

**Flow 4: A forwarded document. (Phase 2.)**

Orchestrator picks a message whose body opens with `-----Original Message-----` — an inline forwarded chain (the reliable forward signal here, since there is no threading header). Reading the body, the orchestrator sees an original preservation notice from counsel that has been forwarded onward to a business team. It weighs whether forwarding to non-lawyers affects the privilege posture, using the inline content directly rather than relying on `find_thread`. It may call `find_thread` as a weak supplement but treats its `confidence: "low"` accordingly. Classifies as relevant; privilege proposed conservatively. If confidence falls below 0.6, the backend converts the proposal to a `request_human_review` regardless.

**What these flows illustrate.**

- `search_documents` is called at the start of a batch (phase 1), rarely during phase 2.
- `read_document` is called on every document in phase 2.
- `check_privilege_signals` is called when content hints (or, when present, participant metadata) suggest privilege — not always.
- `find_thread` is a weak supplement; inline body markers are the primary forward signal.
- `classify_relevance` is called once per document in phase 2.
- `request_human_review` is called on genuine ambiguity, or is auto-inserted by the backend on low confidence.

The typical document consumes 2–4 LLM calls total. A 25-doc batch is 50–100 LLM calls plus a handful of phase-1 searches.

---

## 4. User interaction design

### Cockpit layout

Four regions, laid out as a grid. Sketch this as a 2×2 with one region wider than the others.

**Top left: Queue panel.** The prioritised list of documents the agent will work through in the current batch. Each row shows: doc ID, subject (or "(no subject)" when absent), sender (or "(unknown sender)" when absent), date, current status (pending, in-progress, awaiting review, decided). The document the agent is currently on is highlighted. Status changes update live via SSE.

**Top right (wide): Active document panel.** The document the agent is currently working on, or the one the reviewer has clicked to inspect. Shows subject, participants, date, body. Below the body, the agent's proposed decision (relevance, privilege, issue tags) with confidence scores and a "reasoning" expandable that shows the classification tool's rationale. Below that, three action buttons: Approve, Correct, Request thread context. Because participant and subject fields are often missing in this corpus, the panel must render gracefully with those blank rather than looking broken.

**Bottom left: Agent reasoning stream.** A live log of what the agent is doing right now. Each entry is one iteration: what tool it called, with what arguments, and (once the result comes back) a one-line summary of the result. Auto-scrolls, but with a "pause auto-scroll" toggle so the reviewer can inspect history. This is the "visibility" mechanism made tangible.

**Bottom right: Audit timeline.** A queryable log of all decisions and corrections in the run. Filterable by document, by decision type, by reviewer vs agent origin. Every entry links to the document and the reasoning that produced it. This is the "reversibility" mechanism.

### How each human-in-loop mechanism is realised

**Visibility.** The agent reasoning stream shows every tool call and result in near-real-time. Not "thinking…" — literal tool calls with arguments. When the agent calls `search_documents("shredding retention", ...)`, the reviewer sees that string. When it reads a document, the reviewer sees which document. This is the biggest single differentiator from commercial TAR tools and should feel intentional, not a debug console — style the stream carefully.

**Approval gates.** At the end of every batch (default 25 documents, 5 during dev), and at every explicit `request_human_review` handoff, the loop halts. At batch end, the active document panel switches to a batch summary: N documents proposed for decision, breakdown by relevance/privilege, list of any documents flagged for individual review. Reviewer actions available: "Review individually" (walk through each proposed decision with the option to correct), "Approve all" (commit all proposed decisions as-is), or "Pause run" (halt without committing anything, resume later). Discard-batch was cut — its function is served by reviewing individually and correcting the wrong ones. At a `request_human_review` handoff, the panel shows the single ambiguous document with the reason and the reviewer resolves it inline before the loop resumes.

**Intervention.** During an active batch the reviewer can inspect any document read-only, and can pause the loop entirely. Corrections happen at batch boundaries and at explicit handoffs — not mid-batch. This is a deliberate simplification (see stop conditions in section 2). Once the batch ends or the agent hands off, the correction flow via `POST /corrections` applies: correction is written, summarised into a natural-language note, and injected into the next orchestrator iteration's system prompt. The reasoning stream visibly emits a `correction_applied` event when this happens, so the reviewer sees the correction land before the next document is processed.

**Constraints.** No decision is committed to the production output until the reviewer approves it. The agent's decisions are held with `committed=0` in the decisions table until the reviewer flips them via the API. There is no endpoint that lets the agent commit directly. This is enforced at the schema and API layer, not just by UI convention.

**Reversibility.** The audit timeline is a navigable feature. Every entry has: timestamp, actor (agent or reviewer name), action, target (document, decision, correction), and rationale. Clicking an entry navigates to the document and shows the state at that point in time. Committed decisions can be reversed by opening the entry and clicking "Reverse this decision" — this writes a new decision row with the corrected values and sets `superseded_by` on the old row. Old rows are never deleted. Reversibility is scoped to single-decision reversal; there is no bulk-select or full-run rollback. This is deliberate MVP scope; bulk operations would be a natural feature addition.

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

Not just a scrollable list — a filterable, searchable, linkable navigation surface. Query bar supports filters like `actor:reviewer`, `type:correction`, `doc:3.818908…`, `date:>2001-09-01`. Each entry has a permalink (URL fragment) that scrolls to and highlights that event. When a judge asks "how did you handle this document?" the reviewer types the doc ID and gets every event touching that document, in order.

This is a deliberately overpowered UI for a hackathon, and it's worth the day it takes because it's the most defensible-feeling part of the demo. The "reversibility" story is only credible if the timeline looks like a legal-grade record, not a log console. (If the schedule tightens, the query-language filter bar is the first thing to cut down to a plain filterable list — see section 8.)

---

## 5. Data pipeline

### Corpus source

The corpus is the **EDRM Enron Email Data Set v2, de-duplicated text rendering** (`edrmv2txt-v2.tar.bz2`, ~596MB, from the TREC 2010 Legal Track UMD mirror). It is already downloaded and extracted to `data/raw/`. This is the same collection the TREC 2010 Legal Track qrels were assessed against, which is the entire reason we use it: the evaluation answer key aligns to it by construction (see "Evaluation alignment" below).

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

### Address formats and the CN mapping

Participants appear in three coexisting forms: clean SMTP (`name@enron.com` or external), Exchange X.500 DN (`Name </O=ENRON/OU=…/CN=RECIPIENTS/CN=CODE>`), and bare display name with no address. There is **no directory/alias file in the corpus**, and **no `@enron.com` address exists anywhere for an X.500-addressed person** — the `CN=CODE` fragment resolves only to a *display name*.

Parsing notes for the loader:
- Multi-recipient `To:`/`Cc:` lines are comma-separated, but display names *also* contain commas (`Last, First M.`). Split on the `>,` boundary between `Name </X.500>` units, not on every comma, or names get misattributed to the wrong CN code.
- **Optional enhancement:** a `CN → display-name` map can be derived by scanning all header lines corpus-wide and pairing co-occurring `(CN=code, display name)` fragments (respecting the split rule above). This improves lawyer matching in `check_privilege_signals` but is not required for a first pass. It yields display names only — never emails.

### Encoding and corrupted files

Files are predominantly ASCII (~95%) / UTF-8 (~3%) with CRLF line endings; no high-byte Latin-1/Windows-1252 content was seen in the sample. **However, ~1.7% of files are binary-corrupted** — raw OLE2/MS-Office bytes (including long runs of NUL) leaked into what are nominally plain-text base-email files, not just into attachment parts. Extrapolated, that is on the order of 1,000+ files. **The loader must detect and skip/quarantine non-text `.txt` files defensively** (e.g. reject files with a high NUL-byte ratio or that fail a UTF-8/ASCII decode) rather than assume every `.txt` is parseable. Log skips; do not crash.

### Ingestion script

A single Python script, `ingest.py`, runs once. It:

1. Walks `data/raw/edrm-enron-v2_*.zip/text_NNN/*.txt` (matching `.zip` **directories**, capturing all 159 custodians).
2. **Skips attachment files** (any `.N.txt`) — base emails only.
3. **Skips binary-corrupted files** (NUL-heavy / undecodable), logging each.
4. Parses each file: split header block from body at the first blank line; extract available header fields (`Date`, `X-SDOC`, `X-ZLID` always; `Subject`/`From`/`To`/`Cc` when present); strip the ZL boilerplate footer; capture the body; note any `Attachment:` line for metadata (the attachment itself is not ingested).
5. Normalises participants across the three address forms; stores raw forms plus a canonical key where resolvable. Custodian is taken from the directory name.
6. Inserts into SQLite `documents` (see section 6), with `doc_id` = filename stem.
7. (Optional) Builds the `CN → display-name` map and populates participant-based privilege signals in `privilege_signals` against the hardcoded lawyer list.
8. Chunks the body for embedding — chunks of ~500 tokens with 50 token overlap, one email may produce 1–5 chunks.
9. Embeds each chunk with `sentence-transformers/all-MiniLM-L6-v2` and writes to Chroma with metadata (`doc_id`, `chunk_index`, `sender` when available, `custodian`, `date`).

The script must be idempotent (safe to re-run) and print a summary: documents ingested, files skipped (attachment / corrupt), chunks embedded, parse failures.

**Runtime.** The full base-email corpus is ~455K messages; embedding on CPU with `all-MiniLM-L6-v2` is the bottleneck. Expect it to be the longest single step. For development, ingest a subset (e.g. a handful of custodians, or the first N thousand base emails) and only run the full corpus once, ahead of evaluation/demo. **Note:** any subset used to sanity-check the evaluation must include documents that appear in the Topic 204 qrels (see below), or there will be nothing to score against.

### What goes in SQLite vs Chroma

SQLite is the source of truth for everything structured: documents, participants, privilege signals, agent state, decisions, corrections, audit events. Chroma is a specialised index over email-chunk embeddings and returns doc_ids; the backend then reads the actual document from SQLite. Chroma is never authoritative — if we lose it we can rebuild from SQLite.

### Embedding choice

`sentence-transformers/all-MiniLM-L6-v2` — 384-dim, tiny model, runs on CPU in reasonable time, no API cost. Not the best embeddings available, but for this use case (semantic search inside a fixed corpus) it's ample. Do not use OpenAI or Voyage embeddings unless we have obvious retrieval quality problems.

**Limitations to acknowledge (future-work framing).** `all-MiniLM-L6-v2` is trained on general web text; it works well on Enron because the corpus is business English. Deployment on a domain-specific corpus (medical, patents, non-English) would benefit from a domain-specific or multilingual model. The limitation is domain fit, not embedding quality per se. Worth stating explicitly in the presentation as a real product concern.

### Evaluation methodology (verified against primary sources, revision 3)
 
**Gold standard.** TREC 2010 Legal Track Learning-task judgments:
`qrels.t10legallearn.gz`, 97MB, from `https://trec.nist.gov/data/legal/10/` (mirror:
`https://trec-legal.umiacs.umd.edu/corpora/trec/legal10-results/`). One row per
document per topic (5.48M rows total — hence the size). Format (inferred from the
official toolkit `dolegal10eval.sh` + `calc2.c`; confirm columns on download):
join key `topic:docid`, then stratum ∈ {100, 1000, 10000, 1000000} and
rel ∈ {−1 unjudged, 0 judged non-relevant, 1 judged relevant}. Doc-ids are the
on-disk filename stems — the toolkit's own example doc-id is in exactly that format,
so the join holds by construction. The judged sample per topic is ~2,720 documents,
each assessed by three law-trained reviewers, majority vote. A rel value other than
0/1 is treated as unjudged (TREC coded ~1.25% of documents "broken").
 
**Day-1, first-hour checklist (blocking — do before anything else):**
1. Download and gunzip the qrels; confirm the column layout matches the above.
2. Filter to topic 204, rel ∈ {0,1}; drop doc-ids with a `.N` suffix. Record:
   judged base-email count, relevant count, non-relevant count.
3. Verify the disk join: for a sample of ≥500 judged doc-ids, assert the file
   exists in the doc_id→path index. Expect ~100% (minus binary-quarantined files —
   log any judged doc that got quarantined; these are excluded from metrics and the
   exclusion count is disclosed).
4. Open `seed.csv`; expect the Learning-task seed set (Topic 204: 59 relevant +
   1,132 non-relevant = 1,191 rows). Record its actual schema.
5. Fallback trigger: if judged-relevant base emails for 204 number below ~150, fall
   back to Topic 202 (seed set 1,006 relevant — a much denser topic; same pipeline,
   swap the criteria string and re-run).
**Two metrics, reported separately. Never blended.**
 
*Metric 1 — classification accuracy (the defensibility number).* Eval mode (§2)
classifies judged Topic-204 base emails and scores against the assessor-panel
majority. Report recall first, then precision and F1, always as "on the Topic 204
assessed gold sample, N documents" — never as a population estimate (the sample is
stratified toward documents 2010-era systems ranked highly; we state that).
 
  - **Plan A (default):** classify the entire judged base-email pool. Cost estimate
    at Haiku prices: roughly £5–7. Run a 50-doc pilot first to confirm per-doc cost
    and latency before committing.
  - **Plan B (if the pool is large or budget is tight):** classify ALL
    judged-relevant docs plus a fixed-seed random sample of ~800 judged
    non-relevant. Recall is then exact (every relevant doc evaluated). Precision is
    reported as a derived estimate: precision-in-pool = TP / (TP + FPR × N_nonrel),
    where FPR comes from the non-relevant sample and N_nonrel is the full judged
    non-relevant count. Disclose the construction on the slide's footnote.
  - **Seed hygiene:** exclude any doc-id present in `seed.csv` from reported
    metrics if seeds were used anywhere in prompt development; simplest policy —
    seeds are never placed in prompts, used only for dev sanity checks and demo
    document selection, and the overlap (if any) is excluded regardless.
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
 
**Training-data contamination caveat.** Unchanged from revision 2: a known
limitation of evaluating any large model on a public benchmark; on a fresh private
corpus the numbers are a lower bound argument, since reasoning transfers and
memorised judgments don't. Don't dwell in the video; answer honestly if asked.
 
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
- It has a **healthy gold pool** (~6,362 estimated relevant docs), so precision/recall are stable.
- It keeps **privilege thematically central**: litigation-hold and preservation instructions from counsel are exactly the privileged material a reviewer must protect, so the `check_privilege_signals` story integrates naturally.

Backup: **Topic 202 (FAS 140/125)** if Topic 204's judged base-email pool proves too thin or skewed once `qrels.t10legallearn` is counted. (There is no SPE-specific topic; the original "207 = SPE" framing was incorrect — see `decisions.md`.)

### The lawyer list (demo build vs real deployment)

For the demo the lawyer list is hardcoded: a dozen or so Enron in-house counsel plus external counsel domains. **Given the address reality, each lawyer entry must carry all three keys — display-name variants, `CN=` code(s), and any clean email(s)** — because internal participants have no recoverable email address and matching must succeed on any form. Half a day of research against public sources plus a corpus scan for the CN codes.

**In a real product deployment, this is user-provided.** A legal team knows its own in-house counsel and outside firms — day-one input to any matter. The real product has a matter-setup form (list in-house lawyers by name/email, outside firms by domain, optionally upload a bar directory). This is a strength of the design, not a limitation, and worth stating: the tool respects that the client knows its own privilege universe better than any classifier could infer. The demo compresses matter creation into a preloaded fixture.

---

## 6. State model

SQLite. One database file, `state.db`. Six main tables plus a couple of caches. Every table has a primary key and the FK relationships noted. Types are SQLite affinities; storage is flexible. Enable WAL mode.

### `documents`

Immutable after ingestion. **Base-email documents only** (attachments not ingested).

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
```

Indexes: `thread_id`, `date`, `from_addr`, `custodian`.

Read: `read_document`, `find_thread`, evaluation, UI.
Write: only by `ingest.py`.

**Note on nullability:** `subject`, `from_addr`, `to_addrs`, `cc_addrs` are frequently null by nature of the corpus (see section 5). This is expected, not an ingestion bug. The only unconditionally-reliable fields are `doc_id`, `x_sdoc`, `x_zlid`, `date`, `custodian`, and `body`.

### `privilege_signals` (cache)

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

Read: UI, resumption logic. Write: on run start, on status changes.

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

Read: transcript reconstruction, audit timeline. Write: at the start and end of every tool call.

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
summary           TEXT              -- natural-language form injected into agent context
created_at        TIMESTAMP
created_by        TEXT
```

Read: on every orchestrator iteration (recent N corrections for the run). Write: on `POST /corrections`.

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
payload           TEXT              -- JSON, event-specific
```

Written by a lightweight event writer that other write paths call. Indexed on `run_id`, `target_doc_id`, `event_type`, `timestamp`.

### Read/write pattern during one iteration

1. Orchestrator call begins. Read from SQLite: `agent_runs` (current run state), `agent_steps` for the current `run_id` ordered by iteration DESC LIMIT 3 (the transcript window), `corrections` for the current `run_id` ordered by created_at DESC LIMIT 10.
2. LLM responds with a tool call. Write: `agent_steps` row with `started_at` set, `completed_at` null.
3. Tool executes. Reads its specific tables — `documents` for `read_document`/`find_thread`, `privilege_signals` for `check_privilege_signals`, Chroma plus a `decisions` filter for `search_documents`.
4. Tool returns. Update the `agent_steps` row with `result`, `completed_at`, tokens.
5. If the tool was `classify_relevance`, additionally write a `decisions` row with `committed=0` and an `audit_events` row.
6. Stream SSE events to frontend after each write.

### Why SQLite is enough, and where it would break

Enough because: single-writer (the FastAPI process), small total volume (a few hundred MB of state at most), no concurrent users in the demo scenario. Would break at: multiple concurrent reviewers, multi-machine deployment, or real production with millions of decisions. None applies to a hackathon demo. If a judge asks about scaling, the honest answer is Postgres and a job queue; SQLite is a deliberate choice to save a day.

---

## 7. The demo

Submission is GitHub repo + pitch deck +
demo/pitch video. There is no live judging session. Consequences: the screencast is
not the backup — it is the deliverable; multiple takes are allowed; the 90-second
script below is the video's spine, bookended by ~20s of problem framing and ~20s of
results. Record with the full corpus ingested if the overnight run succeeded,
otherwise on the largest ingested subset (and say the actual number on screen —
never claim 455K if fewer are indexed).

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
[X]% for the reviewer." Then precision, honestly. One contextual line, carefully
phrased as context and not comparison: "this topic was among the hardest in the
original TREC 2010 evaluation — the best research systems recovered under a third of
the relevant documents at a 3% review budget."
 
Right panel: **Projected impact from measured throughput.** [Actual ingested count]
messages; measured agent triage rate of [Y] docs/hour vs the ~50 docs/hour human
baseline; reviewer-hours and cost saved; weeks → days. Every number on this panel is
derived from a measured quantity in the repo.
 
Say: "On a real evaluation set from the TREC Legal Track, the agent flagged [X]% of
the documents expert assessors marked relevant — and a human approved every single
commit."

---

## 8. Path to completion

Opinionated plan. Four days. Two people. One new to agentic AI.

### Stack picks with reasoning

**LLM: Anthropic straight through, no Groq.** Swapping providers midway costs half a day of adapter code and prompt tuning; Anthropic's tool use is more capable than most alternatives; $5–20 in credits handles the full build if we're careful.

**Model choice within Anthropic — dev vs demo strategy.**

- Orchestrator during development: **Haiku.** ~12x cheaper on input, one-line swap, occasional dumber decisions but loop mechanics identical. Use from day 1.
- Orchestrator during evaluation and demo: **Sonnet.** Better reasoning traces, more reliable classification proposals.
- `classify_relevance` tool: **Haiku always**, including in the demo. The classification prompt is narrow and structured; halves per-run LLM cost with negligible quality loss.
- Dev batch size: **5 documents**. Demo batch size: **25**. Config variable from day 1.
- Combined effect: dev batches cost well under $0.50; a full demo/evaluation run under $5.

**Exposing model choice in the UI is cut.** Natural feature, but building it requires evaluating on multiple models (doubling eval work) or shipping without eval on the alternatives (not credible for a defensibility pitch). Add to future work.

**Frontend: React with Vite, not Next.js.** Next.js SSR machinery is friction we don't need for a localhost demo. Vite gives a React dev server in one command. SSE consumption is trivial in either. Half a day saved.

**Backend: FastAPI.** No serious alternative for a Python-first agent build. Use `async` throughout for the SSE endpoint; tool implementations can be sync where they're just DB calls.

**Vector store: Chroma.** More examples online than LanceDB, which matters when the submitter is new to this. Speed difference doesn't matter at this scale.

**State: SQLite with WAL mode enabled.** As specced.

**Agent framework: none.** Do not use LangChain, LangGraph, LlamaIndex, CrewAI, or similar. Anthropic's tool use API is enough. Frameworks add layers that hide what's happening — the opposite of what a transparency pitch needs — and change fast enough that most online examples are stale. The loop in section 2 is roughly 100 lines of Python. Write it directly.

**Deployment: laptop, localhost.** As discussed in section 1.

### Stack picks
 
Unchanged from revision 2: Anthropic native tool use, no framework; Haiku for dev
orchestrator and for `classify_relevance` always; Sonnet orchestrator for the
recorded demo run; FastAPI; React+Vite; Chroma; SQLite (WAL); localhost only.
 
**Budget envelope (£10–15 API):** dev iteration ~£2–3 total (Haiku, batch 5);
eval pilot ~£0.5; full eval Plan A ~£5–7 (Plan B ~£2–3); demo/video runs ~£1–2.
Total ~£9–13. The 50-doc pilot on Day 1 confirms the extrapolation before the big
spend. Rate limits: tier-1 input-tokens-per-minute is the binding constraint on the
eval run — concurrency 5, backoff on 429, expect the full pool to take 1–2 hours
wall-clock. Log tokens per call from the first run.
 
**Embedding hardware:** try `device="cuda"` (sentence-transformers auto-detects; the
4GB GPU is ample for MiniLM) but treat it purely as a speedup — if drivers misbehave
for more than 20 minutes, run CPU and move on. Full-corpus embedding is an overnight
job either way. Disk: SQLite + Chroma together ~5GB; well within limits.
 
### Division of labour
 
Person A (data/eval, full-time): ingestion, qrels, eval mode, metrics, lawyer list.
Person B (loop/UI, ~0.8): agent loop, tools, SSE, cockpit, corrections flow.
Both own the loop conceptually; the spec remains the tie-breaker.
 
### Day 1 — data spine + working loop
 
**Person A, first hour (blocking):** the §5 Day-1 checklist — qrels download, Topic
204 counts, disk join verification, seed.csv inspection, fallback decision (202)
made or dismissed today, not on Day 2.
 
**Person A, morning:** build the doc_id→path index (one full walk of
`data/raw/*.zip` directories — minutes; asserts 159 custodians and 685,592 files).
Write `ingest.py` per §5 rules. Ingest a dev subset: all judged Topic-204 docs +
2–3 custodians as haystack. Embed the subset into Chroma.
 
**Person A, afternoon:** `run_eval.py` + `report_eval.py`. Run the 50-doc pilot:
confirm per-doc cost, latency, and that the classification prompt v1 returns valid
structured output. Sanity-check classifications against a handful of seed.csv
labels. Tune prompt v1 once if grossly off; version the change.
 
**Person A, end of day:** kick off full-corpus ingestion + embedding overnight.
Idempotent, logs skips (attachments, binary-corrupt), prints the summary counts.
 
**Person B, morning:** SQLite schema (§6), FastAPI skeleton, the orchestrator loop
with Anthropic tool use and three tools: `search_documents` (against subset Chroma,
with the review-state filter from day one), `read_document`, `classify_relevance`.
Haiku, batch size 5.
 
**Person B, afternoon:** SSE endpoint + event types (§4); minimal React page
showing the live reasoning stream. Stop conditions 1, 3, 4, 5 (batch complete,
confidence floor, error budget, iteration cap).
 
**End-of-day gate:** the loop iterates end-to-end on the subset and streams to the
browser, and the eval pilot has produced believable numbers on 50 docs. If either
fails, fix it before sleeping — Day 2 has no slack for Day-1 debt.
 
### Day 2 — eval, control mechanisms, cockpit, submission
 
**Person A, morning:** run the full eval (Plan A or B per the pilot's cost check).
While it runs: build `check_privilege_signals` (deterministic; content regexes +
participant matching with `participants_unresolved`). Lawyer list: ~10 known Enron
counsel — start from the lawyer-custodians (Haedicke, Shackleton, Sager, Sanders,
Mann, Taylor, Jones, Nemec, Derrick, Heard), verify names against public sources,
grep the corpus once for each person's CN code and display-name variants. Two hours,
not half a day.
 
**Person A, afternoon:** `report_eval.py` output → results slide numbers. Compute
throughput figures. Select 5–6 demo documents (vivid spoliation content from
seed-relevant docs; one ambiguous retention-schedule doc for the intervention beat;
one privilege-flagged preservation notice).
 
**Person B, morning:** cockpit layout (four regions; render gracefully around
missing subject/sender). `request_human_review` with the asyncio.Event pattern and
inline resolution. Batch approval gates (approve all / review individually).
 
**Person B, afternoon:** corrections flow (`POST /corrections`, template summary,
context injection) + **corrections viewer** (the literal injected text, timestamps,
doc links). Verify a correction visibly lands on the next document's reasoning —
this is the video's money shot; test it three times.
 
**Both, evening — HARD STOP building at ~20:00.** Then, in order: (1) rehearse and
record the demo video (Sonnet orchestrator, batch 25, full or largest-available
corpus; multiple takes until the correction-propagation beat lands cleanly);
(2) deck — problem, solution, cockpit, honest results panel, impact panel, what's
next (privilege qrels, XML metadata, structured rule memory); (3) repo README with
setup instructions and the eval reproduction command. Submission text last.
 
### If behind by Day 2 midday, cut in this order
 
1. Single-decision reversal (stretch already) — audit list becomes read-only.
2. Batch "review individually" walkthrough → approve-all plus per-doc correct
   buttons on the batch summary list.
3. Audit timeline → the SSE event log restyled; no separate table view.
4. Plan A eval → Plan B (all-relevant + non-relevant sample).
Never cut: the qrels join + eval numbers, the corrections flow + viewer, the batch
approval gate, the reasoning stream. Those four are the pitch (Technical 35% +
Control 20% + Demo 20%), and the eval is Impact's (30%) credibility.



### Aggressive defer list

Things not to build. All are legitimate future work; none help the demo:

- Multi-topic support. One topic (204) is enough.
- Multi-reviewer support. Single-user demo.
- Deployment beyond localhost.
- Rule-memory corrections propagation. Context injection only.
- LLM-resummarised corrections at large cap. N=10 fixed.
- Model choice exposed in UI.
- Bulk-select reversibility or full-run rollback. Single-decision reversal only.
- Mid-batch reviewer intervention. Corrections at batch boundaries only.
- `extract_entities` tool. Cut entirely.
- **Attachment ingestion. Base emails only** — attachments (`.N` files) are skipped; the eval is restricted to base-email judgments to match.
- Deriving real `@enron.com` addresses for X.500 participants. Display-name / CN-code matching only.
- Undo/redo beyond the reversal-via-new-decision pattern.
- Discard-batch action.
- Any authentication.
- Any tool that isn't in section 3.
### Aggressive defer list (delta from revision 2)
 
All revision-2 items stand. Additionally cut in revision 3:
- `find_thread` — cut entirely (inline body markers only; §3 status updated).
- Audit-timeline query language / permalinks — plain filterable list.
- CN→display-name corpus-wide map — lawyer list carries hand-collected CN codes.
- Single-decision reversal — stretch, first to cut.
- Pause/resume UI — the schema supports resume; no UI for it.
- `issue_tags` UI — field kept in schema, not surfaced.
New defer-list entries with pointers: privilege evaluation against
`qrel_leg_int_2010_msg_post` (Topic 304); EDRM XML metadata ingestion for real
threading/addresses (~74GB, production path).

### Named risks and mitigations

**Risk: `qrels.t10legallearn` Topic 204 base-email pool is thinner or more skewed than expected.** Mitigation: count it on Day 1 (not Day 3). If too thin, fall back to Topic 202 (FAS 140), which has a comparable gold pool. The doc-id join itself is already verified.

**Risk: participant metadata gaps cripple privilege signals.** From/To are missing on a large fraction of documents and internal people have no email address. Mitigation: this is designed for — `check_privilege_signals` weights content signals (confidentiality markers, legal-advice/preservation language) more heavily and flags `participants_unresolved`. Build the CN→display-name map if time allows to improve coverage; don't block on it.

**Risk: binary-corrupted `.txt` files crash ingestion.** ~1.7% of files carry leaked binary. Mitigation: the loader detects and skips NUL-heavy/undecodable files, logging them. Test this deliberately on a known-bad file (`DATA_REFERENCE.md` §8 names one).

**Risk: enumeration silently drops the two largest custodians.** Mitigation: glob `*.zip` directories, not `*_xml.zip` — the kaminski-v/kean-s split parts (60,723 files) are otherwise missed. Assert the ingested custodian count is 159.

**Risk: Agent loop generates too many tool calls per document, blowing token budget.** Mitigation: log tokens per iteration from day 1. If a single-document classification takes more than 10 iterations, tighten the system prompt. There is a real failure mode where the agent does 30 searches on one document; the prompt should discourage this explicitly.

**Risk: Rate limit during evaluation run.** Mitigation: evaluate against the assessed pool / a sample, not the full corpus. Precision and recall are stable on samples of that size.

**Risk: Privilege classification is embarrassingly wrong live.** Mitigation: fine — use it to make the human-in-loop point. The conservative (over-flag) stance means the failure mode should be "too many things flagged as privileged" rather than "privileged docs missed." Test this deliberately.

**Risk: SSE connection drops during demo.** Mitigation: SSE has native reconnection. Keep the backup screencast ready.

**Risk: Live LLM API outage during demo.** Mitigation: pre-recorded screencast. Do not fight the demo gods.

**Risk: The two of you disagree on a tool boundary or the loop structure late in the build.** Mitigation: this spec is the tie-breaker. If we've changed our minds, update this spec first (and `decisions.md`), then the code. Do not argue in code.



### When to stop building

Hard stop at end of morning on day 4. If a feature isn't working by then, it's cut. Every hour after that is worth two hours of polish and rehearsal — the demo is 20% of the score and the submission text, video, and story are what carries the judgment. A last-minute feature that half-works actively damages all three.
