"""
pop_next_document tool (spec §3 addition, 2026-07-04).

The LLM's Phase-2 entry point: returns one candidate document from the persistent
batch queue at a time, enriched with metadata (subject, sender, date) fetched fresh
from SQL. The LLM then calls read_document / classify_relevance / propose_decision
using the `doc_id` from THIS turn's tool result — no copying from an earlier turn,
no scanning a long list.

WHY THIS TOOL EXISTS. Live-run observation (Haiku): with search results in the
transcript being truncated at 3 iteration pairs, the LLM hallucinated doc_ids by
iteration 7+ (e.g. copied a real prefix and invented the suffix, or typoed one
character). Fix: never make the LLM copy doc_ids from memory. The queue lives on
`AgentRun.current_batch_queue` and the LLM asks for one at a time. Distance
between "receive doc_id" and "use doc_id" collapses to at most a couple of turns.

DESIGN NOTES
- Zero args (aside from `run_id` which the dispatch supplies). The LLM has no
  choice of ordering — the queue is FIFO by search-score rank.
- On empty queue, returns `{"empty": True, "hint": ...}`. The LLM's prompt tells
  it that means "queue drained — do a targeted search or finish_batch".
- Returned metadata is fetched from the Document row, not stored in the queue,
  so a stale queue entry can't render stale metadata. If the doc has vanished
  between the search and this pop (shouldn't happen at demo scale), returns an
  error — the LLM should pop again.
- Does NOT write an AuditEvent — the AgentStep row records that pop_next_document
  was called and what it returned. Enough audit for the demo.

ERRORS
- Unknown run -> {"error": ...}. Caught in dispatch upstream normally.
"""

from __future__ import annotations

import json
import logging

from agent.models import AgentRun
from agent.queue import pop_head
from documents.models import Document

logger = logging.getLogger(__name__)


def _from_display_label(from_display_raw) -> str | None:
    """Prefer resolver-derived canonical display; fall back to raw."""
    if not from_display_raw:
        return None
    try:
        unit = json.loads(from_display_raw) if isinstance(from_display_raw, str) else from_display_raw
    except (ValueError, TypeError):
        return None
    if isinstance(unit, dict) and unit.get("display"):
        return unit["display"]
    return None


def pop_next_document(run_id: str) -> dict:
    if not AgentRun.objects.filter(pk=run_id).exists():
        return {"error": f"pop_next_document: unknown run {run_id}"}

    head = pop_head(run_id)
    if head is None:
        return {
            "empty": True,
            "hint": (
                "Queue is empty. If you have not proposed enough decisions for this batch, "
                "issue a single targeted search_documents call; otherwise call finish_batch."
            ),
        }

    doc_id = head.get("doc_id")
    try:
        doc = Document.objects.only(
            "doc_id", "subject", "from_addr", "from_display", "date"
        ).get(pk=doc_id)
    except Document.DoesNotExist:
        # Stale queue entry (extremely rare — search ran against the same table).
        # Return an error so the LLM pops the next one on its next turn.
        return {"error": f"pop_next_document: doc {doc_id} vanished from corpus; pop again"}

    sender = _from_display_label(doc.from_display) or doc.from_addr or None
    return {
        "doc_id": doc.doc_id,
        "subject": doc.subject,
        "snippet": head.get("snippet") or "",
        "sender": sender,
        "date": doc.date.isoformat() if doc.date else None,
    }
