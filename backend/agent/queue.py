"""
Batch queue helpers — persistent, backed by `AgentRun.current_batch_queue` (JSONField).

The loop feeds `search_documents` hits into the queue via `absorb_search_hits`; the
LLM drains the queue one candidate at a time via the `pop_next_document` tool. The
queue lives in SQL (not memory) so:
  * it survives transcript truncation — the LLM never has to remember doc_ids
  * it survives process crashes — a fresh `run_batch(run_id)` call sees the same queue
  * the frontend can inspect it (`AgentRun.current_batch_queue`)

Entries are compact: `{"doc_id": str, "snippet": str}`. The pop tool enriches each
returned entry with subject / sender / date fetched fresh from the `Document` row —
keeping the persisted payload small and always up-to-date.

Concurrency: single-writer (the loop) at any given moment. No batching or locking
needed at demo scale.
"""

from __future__ import annotations

import logging

from agent.models import AgentRun
from documents.models import Document

logger = logging.getLogger(__name__)

# Cap the queue size so a wild loop can't blow up the JSONField. Search results
# have review-state filtering, so this rarely bites in practice.
MAX_QUEUE_LENGTH = 200


def load_queue(run_id: str) -> list[dict]:
    """Read the current queue for this run. Returns [] on unknown run."""
    try:
        run = AgentRun.objects.only("current_batch_queue").get(pk=run_id)
    except AgentRun.DoesNotExist:
        return []
    return list(run.current_batch_queue or [])


def save_queue(run_id: str, entries: list[dict]) -> None:
    """Overwrite the persisted queue for this run."""
    AgentRun.objects.filter(pk=run_id).update(current_batch_queue=entries)


def absorb_search_hits(run_id: str, hits) -> dict:
    """Merge a `search_documents` result into the persistent queue.

    De-duplicates on `doc_id` — a search that resurfaces a doc already queued
    doesn't add it again. Returns counts so the loop can build a compact LLM-facing
    summary (no doc_ids leaked to the LLM at all — see loop.py for the rationale).
    """
    if not isinstance(hits, list):
        return {"n_added": 0, "n_duplicates": 0, "n_returned": 0, "total_queued": 0}

    queue = load_queue(run_id)
    seen = {e.get("doc_id") for e in queue}
    n_added = n_duplicates = 0

    for hit in hits:
        if not isinstance(hit, dict):
            continue
        doc_id = hit.get("doc_id")
        if not doc_id:
            continue
        if doc_id in seen:
            n_duplicates += 1
            continue
        if len(queue) >= MAX_QUEUE_LENGTH:
            break
        seen.add(doc_id)
        queue.append({
            "doc_id": doc_id,
            "snippet": (hit.get("snippet") or "")[:400],
        })
        n_added += 1

    save_queue(run_id, queue)
    return {
        "n_added": n_added,
        "n_duplicates": n_duplicates,
        "n_returned": len(hits),
        "total_queued": len(queue),
    }


def pop_head(run_id: str) -> dict | None:
    """Remove and return the queue head, or None when empty."""
    queue = load_queue(run_id)
    if not queue:
        return None
    head = queue[0]
    save_queue(run_id, queue[1:])
    return head


def queue_length(run_id: str) -> int:
    return len(load_queue(run_id))
