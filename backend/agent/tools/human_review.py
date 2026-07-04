"""
request_human_review (spec §3) / await_human_resolution (spec §2 Django Option 1).

The synchronisation side of the tool. The loop invokes `request_human_review` via the
dispatch table; that resolves to `await_human_resolution(run_id, doc_id, reason)`, which
persists a `HumanReviewRequest` row and then polls it until a separate
`POST /runs/<run_id>/resolve` writes the resolution. Returns the resolution dict
{decision, reviewer_notes} to the loop, which continues with the correction appended to
the transcript (spec §3 Flow 3).

DESIGN NOTES
- Persistence-before-block matters (§2 Option-1 durability): a crash mid-wait recovers
  from the DB row rather than losing the pending review. The row also carries the
  audit trail (created_at, resolved_at, reason).
- Runs inside the synchronous streaming view generator (WSGI multithreaded runserver).
  The resolving POST is served on ANOTHER worker thread, which writes to the same row;
  this poller sees it via `refresh_from_db` and returns. WAL mode (§6) makes the
  concurrent write + read lock-free.
- No asyncio, no threading primitives — a plain sleep-poll loop is the whole mechanism.
  Cheap: one indexed SELECT every 0.5s. Reviewer speed dominates by ~5 orders of
  magnitude.
- Returns {"error": str} on any failure (bad ids, DB error, timeout) so the loop hands
  the orchestrator a tool_result it can course-correct on (§2 failure modes).
"""

from __future__ import annotations

import logging
import time

from agent.models import AgentRun, HumanReviewRequest
from documents.models import Document

logger = logging.getLogger(__name__)

# Poll interval — spec §2 "sleep a fraction of a second, re-query, repeat". Half a
# second gives snappy resume without pathological load; a reviewer never notices.
POLL_INTERVAL_SECONDS = 0.5

# Safety cap on the wait. A demo review is measured in seconds; 30 minutes is the
# outer bound where "reviewer walked away" becomes more likely than "reviewer is
# thinking". Kept explicit so a pathological hang surfaces rather than parks a
# process forever.
DEFAULT_TIMEOUT_SECONDS = 30 * 60


def await_human_resolution(
    run_id: str,
    doc_id: str,
    reason: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> dict:
    """Block until a human resolves this handoff, or timeout.

    On success, returns the reviewer's resolution as `{decision: {...},
    reviewer_notes: str}` (spec §3). On any failure (unknown run/doc, DB error,
    timeout) returns `{"error": str}` so the loop can continue rather than raise
    into the streaming generator.
    """
    if not run_id:
        return {"error": "human_review: missing run_id"}
    if not doc_id:
        return {"error": "human_review: missing doc_id"}

    # Fail fast on bad ids — a broken dispatch shouldn't create orphan pending rows
    # the reviewer then has to hunt down in the UI.
    if not AgentRun.objects.filter(pk=run_id).exists():
        return {"error": f"human_review: unknown run {run_id}"}
    if not Document.objects.filter(pk=doc_id).exists():
        return {"error": f"human_review: unknown document {doc_id}"}

    try:
        review = HumanReviewRequest.objects.create(
            run_id_id=run_id,
            doc_id_id=doc_id,
            reason=reason or "",
        )
    except Exception as e:
        logger.exception("human_review: failed to create pending row")
        return {"error": f"human_review: persistence failed - {e}"}

    logger.info(
        "human_review: parked run=%s doc=%s request_id=%s",
        run_id, doc_id, review.request_id,
    )

    deadline = time.monotonic() + timeout_seconds
    while True:
        review.refresh_from_db()
        if review.resolved_at is not None:
            resolution = review.resolution or {}
            logger.info(
                "human_review: resumed run=%s doc=%s request_id=%s",
                run_id, doc_id, review.request_id,
            )
            return {
                "decision":       resolution.get("decision") or {},
                "reviewer_notes": resolution.get("reviewer_notes") or "",
            }
        if time.monotonic() >= deadline:
            logger.warning(
                "human_review: timeout after %.0fs run=%s doc=%s request_id=%s",
                timeout_seconds, run_id, doc_id, review.request_id,
            )
            return {
                "error": (
                    f"human_review: timed out after {int(timeout_seconds)}s "
                    f"waiting for reviewer resolution"
                )
            }
        time.sleep(poll_interval)
