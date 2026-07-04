"""
propose_decision tool (spec §3, terminal per-doc action).

Every document the agent reviews ends with a `propose_decision` call. The tool
persists one `Decision` row (`committed=0`, `proposed_by="agent"`) and returns a
compact `{ok, decision_id, relevant, privilege, confidence, reasoning}` acknowledgement
so the LLM knows the record landed and can continue with the next document.

NOT COMMITTED. The `committed` flag is the enforcement point for the "humans commit"
invariant (§4). It flips 0->1 only via `POST /decisions/<id>/commit`, which is
reviewer-gated. This tool never touches `committed`.

CONFIDENCE FLOOR lives IN THE LOOP, not here. The loop inspects the returned
`confidence` and, if it is below the threshold, invokes `await_human_resolution` and
writes a superseding reviewer row (§2 stop condition 3). Keeping the auto-handoff in
the loop preserves SSE visibility — the loop can yield `human_review_requested` before
blocking on the reviewer, which a tool-internal handoff could not do.

BATCH ARITHMETIC also lives IN THE LOOP. This tool is a simple recorder.

ERRORS
- Unknown run/doc -> {"error": ...}. The loop's dispatch already carries `run_id`, so
  this only fires on a bad LLM `doc_id`.
- Missing / malformed fields fall back to safe defaults (`unclear` privilege, `[]`
  tags, 0.0 confidence). The loop's error budget catches persistent misuse.
"""

from __future__ import annotations

import logging

from agent.models import AgentRun, Decision
from documents.models import Document

logger = logging.getLogger(__name__)

# Values accepted for Decision.privilege (§6). Anything else -> "unclear" (§3
# conservative-privilege stance: err toward flagging uncertain material).
PRIVILEGE_VALUES = {"privileged", "not_privileged", "unclear"}

# Guard on reasoning length. Decision.reasoning is TextField (unbounded), but a
# runaway LLM could still write a novel; cap to keep the audit UI readable.
MAX_REASONING_CHARS = 8000


def propose_decision(
    run_id: str,
    doc_id: str,
    relevant: bool,
    privilege: str = "unclear",
    issue_tags: list | None = None,
    confidence: float = 0.0,
    reasoning: str = "",
) -> dict:
    """Persist one agent-proposed decision. Returns the acknowledgement the LLM sees.

    Returns `{"error": str}` on unknown ids so the loop can surface a `tool_result`
    with `is_error=true` and let the LLM course-correct (spec §2 failure modes).
    """
    if not AgentRun.objects.filter(pk=run_id).exists():
        return {"error": f"propose: unknown run {run_id}"}
    if not Document.objects.filter(pk=doc_id).exists():
        return {"error": f"propose: unknown document {doc_id}"}

    # Coerce / clamp the LLM's fields defensively.
    if privilege not in PRIVILEGE_VALUES:
        privilege = "unclear"
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if not isinstance(issue_tags, list):
        issue_tags = []

    decision = Decision.objects.create(
        run_id_id=run_id,
        doc_id_id=doc_id,
        proposed_by="agent",
        relevance=bool(relevant),
        privilege=privilege,
        issue_tags=issue_tags,
        confidence=confidence,
        reasoning=(reasoning or "")[:MAX_REASONING_CHARS],
        committed=False,
    )
    logger.info(
        "propose: recorded decision_id=%s run=%s doc=%s relevant=%s privilege=%s confidence=%.2f",
        decision.decision_id, run_id, doc_id, relevant, privilege, confidence,
    )
    return {
        "ok": True,
        "decision_id": decision.decision_id,
        "relevant": bool(relevant),
        "privilege": privilege,
        "confidence": confidence,
        "reasoning": reasoning or "",
    }
