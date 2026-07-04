# E-Discovery Review Agent

**UK AI Agent Hackathon EP5 — Conduct.ai Track ("Make Legacy Move")**

An AI-assisted e-discovery cockpit that keeps a human reviewer in full control of the agent doing the work.

---

## The business case

When a company is sued, subpoenaed, or investigated, it has to hand over every document relevant to the dispute — and *only* those documents, with anything covered by legal privilege withheld. That process is **e-discovery**: a human review team reads through tens or hundreds of thousands of emails and files, tags each one relevant or not, flags privilege, and produces a defensible, auditable record of every decision for opposing counsel and the court.

Today this is done by rooms of paralegals and junior lawyers at $100–400/hour, taking weeks to months per matter, at a cost that runs into the millions for large litigation. It is slow, repetitive, and the biggest risk isn't missing a document — it's producing a privileged one by mistake, or being unable to explain *why* a decision was made months later when a judge asks.

This project is a working prototype of what the next generation of that process looks like: an AI agent does the reading, searching, and first-pass classification at machine speed, while a human reviewer stays firmly at the wheel — watching every step, approving or overriding every decision, and building a legally defensible audit trail as a byproduct of normal use rather than an afterthought.

The platform handles the full lifecycle of a review, in one place:

- **Viewing** —  surfacing and rendering real, messy source documents in a human-readable form. Recovers from missing fields, malformed records, and tool errors instead of falling over.
- **Deciding** — AI-proposed relevance and privilege calls, reviewed and committed (or overridden) by a person. The agent never commits a decision unsupervised. Every step is visible, reversible, and gated behind a human click.

- **Auditing** — every decision, correction, and piece of reasoning permanently logged, attributable to who decided what and why.
- **Exporting** — a final, defensible list of decisions ready to hand to counsel or the court.

*[Screenshot: full cockpit view — queue, active document, live reasoning stream, and audit timeline side by side]*

---


## Key features

**Transparency.** Every tool call the agent makes — every search, every document read, every privilege check — streams live to the interface as it happens. Nothing happens in a black box; the reviewer sees the agent's reasoning unfold in real time, not a summary after the fact.

**Control.** The agent proposes; it never commits. Low-confidence or ambiguous calls are automatically routed to a human for a decision. The reviewer can accept, override, or redirect the agent at every batch boundary — control beats autonomy, by design, not by accident.

**Traceability.** Every committed decision carries a permanent, structured record of who decided it, when, and why — built for a legal environment where "the AI said so" is not an acceptable answer months later in front of a judge.

**Speed.** What takes a human review team days or weeks per batch happens in minutes, with the numbers to prove it (see [Evaluation](#evaluation-section-g) below).

**Resilience.** Real enterprise data is never clean. This project is built and evaluated on genuinely messy, real-world source data — not a curated demo set — and is designed to degrade gracefully (missing fields, unresolvable participants, corrupted files) rather than break.

---

## Feature tour

### 1. A persistent, self-populating review queue
The agent searches the corpus and builds its own queue of candidate documents for the reviewer to work through. That queue lives in the database, not in memory — if the session ends abruptly (browser closed, server restarted, laptop dies mid-demo), nothing is lost. The reviewer picks up exactly where they left off.

*[Screenshot: the review queue / actions table, mid-batch]*

### 2. Real-world messy data, made human-readable
The underlying corpus (see [Data](#the-data) below) is real, unstructured, and genuinely messy: missing senders, unresolvable internal addresses, inconsistent formatting, occasional corrupted files. The platform resolves what it can (structured participant matching, forwarded-message detection) and renders the rest honestly rather than hiding the mess — so a reviewer sees a clean, legible document view even when the source data underneath is anything but.

*[Screenshot: a rendered document view next to a snippet of the raw source file]*

### 3. Transparency: live streaming of every tool the agent uses
The agent's tool calls — search, read, privilege check, classify — stream to the UI the moment they happen, over a live connection, not a poll. The reviewer watches the agent's reasoning trace build in real time: what it searched for, what it read, what it noticed, and why it proposed the decision it did.

*[Screenshot: the live reasoning / tool-call stream panel]*

### 4. A fixed, legally-defensible audit log
Every decision — agent-proposed or human-committed — is written to a permanent audit timeline: who (agent or reviewer) decided what, when, and the stated reason. This is built to support multiple reviewers collaborating on the same matter, with full traceability back to the exact document, decision, and rationale — the format a legal team would actually need to hand to opposing counsel or a court.

*[Screenshot: the audit timeline, showing a mix of agent proposals and human overrides]*

### 5. The reviewer can always change their mind
No decision is permanent until it's committed, and corrections are a first-class action, not an edge case. When a reviewer overrides the agent, that correction is captured, summarised, and fed back into the agent's context — so the next similar document benefits from the guidance immediately. Reviewers can see exactly what corrections the agent currently "knows" at any point.

*[Screenshot: the corrections view — a reviewer override and its effect on the next document]*

### 6. See what the agent sees — and overrule it
The active document panel always shows exactly the document the agent is currently reasoning about, in the same view the reviewer uses to judge it. The reviewer can step in at any point and overwrite the agent's proposed decision directly, with the override immediately reflected in the audit trail.

*[Screenshot: the active document panel with an in-progress AI proposal and the override control]*

### 7. Speed, measured
See [Evaluation](#evaluation-section-g) for the full methodology, but the headline: thousands of documents classified against real legal ground truth in minutes, at a cost of a few dollars, versus the days-to-weeks and thousands of dollars a human review team would spend on the same volume.

*[Screenshot / chart: throughput and cost comparison, agent vs. manual baseline]*

---

## The data

We evaluate against the **EDRM Enron v2** email corpus — real, messy, de-identified corporate email, not a synthetic or cherry-picked dataset — scored against **TREC 2010 Legal Track** Topic 204 (document destruction, retention, and shredding), a genuine legal-industry benchmark with expert-adjudicated ground truth. No documents are hand-labelled by us; the standard is external and independently verifiable. See [`docs/ediscovery-technical-spec.md`](docs/ediscovery-technical-spec.md) for the full data model, corpus provenance, and known data-quality realities (missing headers, unresolvable internal addresses, occasional corrupted files) and how the system handles each.

---

## Evaluation 

Headless accuracy evaluation for the agent's `classify_relevance` tool, separate
from the live cockpit loop. See [`docs/ediscovery-technical-spec.md`](docs/ediscovery-technical-spec.md) §2 "Eval
mode" and §8-G for the full design.

**What's being measured.** TREC 2010 Legal Track Topic 204 (document
destruction / retention / shredding) on the EDRM Enron v2 corpus. Every judged
Topic-204 base email is classified by `classify_relevance` (Haiku, prompt v1,
the same tool and criterion the cockpit uses) and scored against the official
TREC gold labels (`qrels.t10legallearn`). No manual labelling; nothing here is
a human-committed decision — eval mode never sets `Decision.committed`.

**Scripts** (`backend/`):

- `eval_gold.py` — shared gold-label loading (topic filter, seed-overlap
  exclusion) used by both scripts below, so they can't diverge on which
  doc-ids count.
- `run_eval.py` — headless classification run. Supports `--plan a` (full
  judged pool, ~2,028 docs) or `--plan b` (all relevant + a fixed
  non-relevant sample), `--pilot N` for a cost/latency pilot, and is
  resumable (skips doc-ids that already have a decision under the run).
- `report_eval.py` — scores a run's decisions against the qrels gold,
  subtracts the seed/judged overlap (per the seed-hygiene rule), and writes
  `results.json`.

**Corpus / pool sizes** (verified, not placeholders):

| Quantity | Count |
|---|---|
| Topic 204 judged base emails | 2,028 |
| — relevant | 387 |
| — non-relevant | 1,641 |
| Seed ∩ judged overlap (excluded from scoring) | 47 |

**Results — full Plan A run (`eval-plan-a-204`), Haiku 4.5, prompt v1:**

| Metric | Value |
|---|---|
| Recall | 0.7500 |
| Precision | 0.7994 |
| F1 | 0.7739 |
| Confusion (TP / FP / FN / TN) | 267 / 67 / 89 / 1,557 |
| Recall ceiling (empty-bodied gold-relevant docs) | 88.76% (316/356 scorable relevant) |
| Docs scored | 1,980 of 1,981 (1 doc's raw file is binary-corrupt, skipped) |

Not directly comparable to TREC 2010 system scores — those measure ranked-retrieval
recall at a pool cutoff; this measures classification accuracy over the full judged
pool. No same-axis claim is being made.

**Cost / throughput** (full run, 2,027 docs classified, Haiku 4.5):

| Quantity | Value |
|---|---|
| Tokens (in / out) | 3,348,771 / 358,296 |
| Total cost | ~$5.14 |
| Cost per doc | ~$0.0025 |
| Throughput | ~145 docs/min |
| Wall-clock | ~14 min |

Reproduce: from `backend/`, `python run_eval.py --plan a` then
`python report_eval.py --run-id eval-plan-a-204`. Full output: `backend/results.json`.

## Architecture at a glance

- **Backend:** Django + Django REST Framework, SQLite, Chroma vector index.
- **Frontend:** React + Vite + MUI.
- **Agent loop:** a single Django streaming view running the orchestrator loop, using Anthropic's native tool use — no agent framework (LangChain/LangGraph, etc.) in the stack.
- **Models:** Haiku for development and the classifier tool; Sonnet for evaluation and demo runs (config, not hardcoded).

Full architecture, tool specifications, schema, and the reasoning behind every major decision live in [`docs/ediscovery-technical-spec.md`](docs/ediscovery-technical-spec.md) (source of truth) and [`docs/decisions.md`](docs/decisions.md) (why choices were made).

---

## Quick start

### Backend

#### Linux / macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

#### Windows

```bash
cd backend
python3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173/.

---


