"""
Agent loop — orchestrator turn / tool dispatch / stop conditions (spec §2).

Shape: a Python generator that yields SSE-shaped event dicts. The streaming view
(GET /runs/<run_id>/stream, not yet built) wraps this in `StreamingHttpResponse` and
formats each yielded dict as `event: <type>\\ndata: <json>\\n\\n`. The generator
form makes the loop testable without HTTP.

Each yielded event is `{"type": <event_type>, "data": <payload dict>}`. Event types
mirror spec §4:
  run_started · step_started · step_completed · document_decision_proposed ·
  human_review_requested · batch_complete · run_error · run_paused

WHAT FEEDS IN (freshly read at the start of each batch)
  - AgentRun row  : topic, criteria, batch_size — persistent config for this run
  - Correction rows (last N=10 for this run) — reviewer's rolling guidance, injected
    into the orchestrator's system prompt (§2 corrections propagation)

WHAT COMES OUT (during the batch)
  - AgentStep row per tool call (arguments, result, tokens, error, timing)
  - Decision row per per-document proposal (committed=0 until the reviewer commits)
    plus a superseding reviewer row on confidence-floor auto-handoff
  - HumanReviewRequest row per handoff — LLM-initiated OR backend confidence-floor
  - SSE events streamed live to the frontend

STOP CONDITIONS (§2)
  1. finish_batch tool call from the LLM (voluntary)
  2. Reached batch_size proposals (backend-enforced)
  3. Confidence floor breach → auto-handoff to reviewer (handled per-proposal, does
     NOT stop the batch)
  4. Tool errors 3× on the same tool → halt with run_error
  5. 3 consecutive LLM turns without a tool call → halt with run_error
  6. Iteration cap → yield run_paused (should never fire in normal use)

TRANSCRIPT TRUNCATION
  Anthropic's messages API requires tool_use / tool_result pairing to stay intact.
  `_truncate` keeps the last N assistant turns AND their following user turns, so
  every retained tool_use has its matching tool_result.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import defaultdict
from typing import Iterator

import anthropic
from django.utils import timezone

from agent.models import AgentRun, AgentStep, Correction, Decision
from agent.prompts import build_orchestrator_system_prompt
from agent.tools import execute_tool
from agent.tools.human_review import await_human_resolution
from api.serializers import _VALUE_PATTERN

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Config                                                                       #
# --------------------------------------------------------------------------- #

# Haiku dev, Sonnet demo — one env-var swap (§8 stack picks).
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-3-5-haiku-latest")
MAX_OUTPUT_TOKENS = 2048

# §2 stop conditions
MAX_ITERATIONS = 100
TOOL_ERROR_BUDGET = 3
MALFORMED_STREAK_BUDGET = 3
CONFIDENCE_FLOOR = 0.60

# §2 corrections propagation
CORRECTIONS_INJECT_N = 10

# §2 transcript window — last 3 iteration pairs (assistant + tool_result)
MAX_TRANSCRIPT_PAIRS = 3

# Rate-limit / transient-error backoff (mirrors classify.py)
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2.0


# --------------------------------------------------------------------------- #
# LLM client — lazy so `manage.py migrate` doesn't need ANTHROPIC_API_KEY      #
# --------------------------------------------------------------------------- #

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _messages_with_backoff(**kwargs):
    """client.messages.create with exponential backoff + jitter on rate limits,
    transient connection errors, and 529 overload. Re-raises after MAX_RETRIES."""
    delay = INITIAL_BACKOFF_SECONDS
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _get_client().messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            last_exc, reason = e, type(e).__name__
        except anthropic.APIStatusError as e:
            if getattr(e, "status_code", None) != 529:
                raise
            last_exc, reason = e, "overloaded_529"
        if attempt >= MAX_RETRIES:
            raise last_exc
        sleep_for = delay + random.uniform(0, delay * 0.25)
        logger.warning(
            "loop: %s - retry %d/%d in %.1fs", reason, attempt + 1, MAX_RETRIES, sleep_for
        )
        time.sleep(sleep_for)
        delay *= 2
    raise last_exc


# --------------------------------------------------------------------------- #
# Tool schemas — what the LLM sees                                             #
# --------------------------------------------------------------------------- #
# Deliberate design choices:
#   * classify_relevance exposes ONLY doc_id (decisions.md 2026-07-03 Decision 1).
#   * propose_decision is the terminal per-doc action (§3 implicit).
#   * finish_batch is a nullary tool call — the batch-end signal from the LLM.

TOOLS = [
    {
        "name": "search_documents",
        "description": (
            "Semantic search over the email corpus. Returns up to 20 candidate documents "
            "ranked by similarity to the query. Use in Phase 1 to populate the batch queue; "
            "rarely in Phase 2."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query.",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional metadata filters.",
                    "properties": {
                        "date_range": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Two ISO date strings: [start, end].",
                        },
                        "custodian": {"type": "string"},
                        "sender_domain": {"type": "string"},
                    },
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Fetch one document by id. Returns subject, from, to, cc, date, body, "
            "custodian, and resolved participant units."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "check_privilege_signals",
        "description": (
            "Deterministic privilege triage: known lawyers among participants, "
            "confidentiality / legal-advice markers in the body, forward markers. "
            "Call when content or participants hint at privilege — not on every document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "classify_relevance",
        "description": (
            "LLM-powered responsiveness classifier. Returns "
            "{relevant, confidence, reasoning, key_passages}. The topic criterion is "
            "injected by the loop; you supply only the document id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "propose_decision",
        "description": (
            "Record your proposed decision for one document. Call this AFTER "
            "classify_relevance (and check_privilege_signals if you called it) so the "
            "batch counter advances. Nothing is committed — the reviewer approves each "
            "proposal at batch end. If your overall confidence is below 0.6 the backend "
            "will automatically route the document to the reviewer for a final answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "relevant": {
                    "type": "boolean",
                    "description": "Whether the document is responsive to the topic criterion.",
                },
                "privilege": {
                    "type": "string",
                    "enum": ["privileged", "not_privileged", "unclear"],
                    "description": (
                        "Privilege posture. Err toward flagging (privileged / unclear) — "
                        "the reviewer approves each call."
                    ),
                },
                "issue_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional topic-specific tags. Empty list is fine.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Your calibrated overall confidence in this proposal, 0.0–1.0.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One to three sentences combining your relevance and privilege rationale.",
                },
            },
            "required": ["doc_id", "relevant", "privilege", "confidence", "reasoning"],
        },
    },
    {
        "name": "request_human_review",
        "description": (
            "Hand this document off to the reviewer. Use only when responsiveness or "
            "privilege turns on context the document itself does not make explicit. "
            "Provide a specific reason."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["doc_id", "reason"],
        },
    },
    {
        "name": "finish_batch",
        "description": (
            "End the current review batch. Call after you have proposed decisions for "
            "approximately batch_size documents."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _load_recent_corrections(run_id: str, n: int = CORRECTIONS_INJECT_N) -> list[str]:
    """Read the last N reviewer corrections for this run; extract the reasoning
    field from the packed string format used by `Correction.corrected_value`
    (`rel: 1, priv: 0, reason: "..."`). Returns plain strings for the orchestrator
    prompt's `RECENT GUIDANCE` section (§2 corrections propagation).
    """
    values = (
        Correction.objects.filter(run_id_id=run_id)
        .order_by("-corrected_at")
        .values_list("corrected_value", flat=True)[:n]
    )
    out: list[str] = []
    for value in values:
        match = _VALUE_PATTERN.match(value or "")
        if match:
            reasoning = match.group(3).strip()
            if reasoning:
                out.append(reasoning)
    return out


def _truncate(messages: list[dict], max_pairs: int = MAX_TRANSCRIPT_PAIRS) -> list[dict]:
    """Keep the last `max_pairs` assistant turns AND their following user turns.

    Anthropic's messages API rejects an assistant tool_use whose matching user
    tool_result was dropped. Slicing at an assistant boundary preserves pairs.
    """
    if not messages:
        return messages
    assistant_positions = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    if len(assistant_positions) <= max_pairs:
        return messages
    keep_from = assistant_positions[-max_pairs]
    return messages[keep_from:]


def _write_step(run_id: str, iteration: int, tool: str, arguments: dict) -> int:
    step = AgentStep.objects.create(
        run_id_id=run_id,
        iteration=iteration,
        tool=tool,
        arguments=arguments,
    )
    return step.step_id


def _update_step(
    step_id: int,
    result=None,
    error: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
) -> None:
    AgentStep.objects.filter(pk=step_id).update(
        result=result,
        error=error,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        completed_at=timezone.now(),
    )


def _strip_usage(result):
    """`classify_relevance` returns an internal `_usage` telemetry key with token
    counts. Fold it into AgentStep.tokens_* and strip before it becomes tool_result
    content — the LLM shouldn't see it."""
    if isinstance(result, dict) and "_usage" in result:
        usage = result["_usage"]
        return {k: v for k, v in result.items() if k != "_usage"}, usage
    return result, None


def _summarize_result(tool: str, result) -> str:
    """Short one-line summary for the SSE `step_completed` event. Full result stays
    in AgentStep.result for the audit trail; this is the reasoning-stream label."""
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error'][:150]}"
    if isinstance(result, list):
        return f"{len(result)} hits"
    if isinstance(result, dict):
        if tool == "classify_relevance":
            return f"relevant={result.get('relevant')}, confidence={result.get('confidence', 0):.2f}"
        if tool == "propose_decision":
            return (
                f"decision_id={result.get('decision_id')}, "
                f"relevant={result.get('relevant')}, "
                f"privilege={result.get('privilege')}, "
                f"confidence={result.get('confidence', 0):.2f}"
            )
        if tool == "check_privilege_signals":
            return f"strength={result.get('overall_signal_strength')}"
        if tool == "read_document":
            subj = result.get("subject") or "(none)"
            body = result.get("body") or ""
            return f"subject={subj!r}, body={len(body)} chars"
        if tool == "request_human_review":
            return "reviewer resolved"
    return str(result)[:200]


def _tool_result_message(tool_use_id: str, content, is_error: bool = False) -> dict:
    """Format a user-role tool_result message for the LLM's next turn."""
    payload = content if isinstance(content, str) else json.dumps(content, default=str)
    block: dict = {"type": "tool_result", "tool_use_id": tool_use_id, "content": payload}
    if is_error:
        block["is_error"] = True
    return {"role": "user", "content": [block]}


# --------------------------------------------------------------------------- #
# The loop                                                                     #
# --------------------------------------------------------------------------- #

def run_batch(run_id: str) -> Iterator[dict]:
    """Run one batch of the agent loop. Generator of SSE-shaped events.

    Yields events as dicts: `{"type": <event>, "data": <payload>}`. A structural
    failure yields `run_error` and returns; a clean finish yields `batch_complete`;
    the iteration cap yields `run_paused`.
    """
    try:
        run = AgentRun.objects.get(pk=run_id)
    except AgentRun.DoesNotExist:
        yield {"type": "run_error", "data": {"error_type": "unknown_run", "message": f"no run {run_id}"}}
        return

    yield {
        "type": "run_started",
        "data": {"run_id": run_id, "topic": run.topic, "batch_size": run.batch_size},
    }

    corrections = _load_recent_corrections(run_id)
    system_prompt = build_orchestrator_system_prompt(
        criteria=run.criteria,
        batch_size=run.batch_size,
        recent_corrections=corrections,
    )

    messages: list[dict] = []
    proposed_this_batch = 0
    tool_error_counts: dict[str, int] = defaultdict(int)
    malformed_streak = 0

    for iteration in range(1, MAX_ITERATIONS + 1):
        # ---- Orchestrator turn ---- #
        try:
            response = _messages_with_backoff(
                model=DEFAULT_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=_truncate(messages),
            )
        except anthropic.APIError as e:
            yield {"type": "run_error", "data": {"error_type": "llm_api", "message": str(e)}}
            return
        except Exception as e:
            logger.exception("loop: unexpected LLM error")
            yield {"type": "run_error", "data": {"error_type": "llm_unexpected", "message": str(e)}}
            return

# ^^ fill in system_prompt for now

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            malformed_streak += 1
            if malformed_streak >= MALFORMED_STREAK_BUDGET:
                yield {
                    "type": "run_error",
                    "data": {
                        "error_type": "malformed_streak",
                        "message": f"{MALFORMED_STREAK_BUDGET} consecutive turns without a tool call",
                    },
                }
                return
            # Nudge the LLM and try again. Plain text user message is allowed.
            messages.append({"role": "user", "content": "Please call a tool."})
            continue
        malformed_streak = 0

        block = tool_use_blocks[0]  # spec: at most one tool per iteration

        # ---- LLM voluntary finish_batch ---- #
        if block.name == "finish_batch":
            yield {
                "type": "batch_complete",
                "data": {"proposed": proposed_this_batch, "reason": "llm_finished"},
            }
            return

        # ---- Persist AgentStep (started) + SSE step_started ---- #
        arguments = dict(block.input)
        step_id = _write_step(run_id, iteration, block.name, arguments)
        yield {
            "type": "step_started",
            "data": {"step_id": step_id, "tool": block.name, "arguments": arguments},
        }

        # Emit human_review_requested BEFORE the tool blocks on the reviewer — the
        # frontend needs the event to render the handoff panel while the poll waits.
        if block.name == "request_human_review":
            yield {
                "type": "human_review_requested",
                "data": {
                    "doc_id": arguments.get("doc_id"),
                    "reason": arguments.get("reason"),
                    "origin": "agent",
                },
            }

        # ---- Execute the tool ---- #
        try:
            result = execute_tool(block.name, arguments, run_id)
        except Exception as e:
            logger.exception("loop: tool dispatch raised on %s", block.name)
            _update_step(step_id, error=str(e))
            yield {
                "type": "step_completed",
                "data": {"step_id": step_id, "result_summary": f"exception: {e}"},
            }
            tool_error_counts[block.name] += 1
            if tool_error_counts[block.name] >= TOOL_ERROR_BUDGET:
                yield {
                    "type": "run_error",
                    "data": {
                        "error_type": "tool_error_budget",
                        "message": f"{block.name} failed {TOOL_ERROR_BUDGET} times",
                    },
                }
                return
            messages.append(_tool_result_message(block.id, f"exception: {e}", is_error=True))
            continue

        # Fold token telemetry into AgentStep; strip it from the LLM-visible result.
        cleaned, usage = _strip_usage(result)
        tokens_input = usage.get("input_tokens") if usage else None
        tokens_output = usage.get("output_tokens") if usage else None

        if isinstance(cleaned, dict) and "error" in cleaned:
            _update_step(step_id, result=cleaned, error=cleaned.get("error"))
            tool_error_counts[block.name] += 1
        else:
            _update_step(step_id, result=cleaned, tokens_input=tokens_input, tokens_output=tokens_output)
            tool_error_counts[block.name] = 0

        yield {
            "type": "step_completed",
            "data": {"step_id": step_id, "result_summary": _summarize_result(block.name, cleaned)},
        }

        if tool_error_counts[block.name] >= TOOL_ERROR_BUDGET:
            yield {
                "type": "run_error",
                "data": {
                    "error_type": "tool_error_budget",
                    "message": f"{block.name} failed {TOOL_ERROR_BUDGET} times",
                },
            }
            return

        # ---- Post-tool: propose_decision + confidence-floor auto-handoff ---- #
        if block.name == "propose_decision" and isinstance(cleaned, dict) and cleaned.get("ok"):
            doc_id = arguments.get("doc_id")
            confidence = cleaned.get("confidence", 0.0)

            if confidence < CONFIDENCE_FLOOR:
                # Backend-enforced auto-handoff (§2 stop condition 3). Emit the SSE,
                # then block on the reviewer. Reviewer's answer supersedes the agent's.
                reason = (
                    f"agent proposed with confidence {confidence:.2f} "
                    f"(< floor {CONFIDENCE_FLOOR:.2f}): "
                    f"{(cleaned.get('reasoning') or '')[:200]}"
                )
                yield {
                    "type": "human_review_requested",
                    "data": {"doc_id": doc_id, "reason": reason, "origin": "confidence_floor"},
                }
                override = await_human_resolution(run_id, doc_id, reason)
                if "error" in override:
                    yield {
                        "type": "run_error",
                        "data": {"error_type": "handoff_failed", "message": override["error"]},
                    }
                    return

                r_decision = override.get("decision") or {}
                agent_row = Decision.objects.get(pk=cleaned["decision_id"])
                reviewer_row = Decision.objects.create(
                    run_id_id=run_id,
                    doc_id_id=doc_id,
                    proposed_by="reviewer",
                    relevance=bool(r_decision.get("relevance", agent_row.relevance)),
                    privilege=r_decision.get("privilege", agent_row.privilege),
                    issue_tags=r_decision.get("issue_tags", agent_row.issue_tags),
                    confidence=float(r_decision.get("confidence", 1.0)),
                    reasoning=(
                        override.get("reviewer_notes") or r_decision.get("reasoning") or ""
                    )[:8000],
                    committed=False,
                )
                # Mark the agent's row as superseded so the audit trail links them.
                agent_row.superseder_id_id = reviewer_row.decision_id
                agent_row.save(update_fields=["superseder_id"])

                proposed_this_batch += 1
                yield {
                    "type": "document_decision_proposed",
                    "data": {
                        "doc_id": doc_id,
                        "decision_id": reviewer_row.decision_id,
                        "relevance": reviewer_row.relevance,
                        "privilege": reviewer_row.privilege,
                        "confidence": reviewer_row.confidence,
                        "proposed_by": "reviewer",
                        "reviewer_notes": override.get("reviewer_notes") or "",
                        "superseded_agent_decision_id": agent_row.decision_id,
                    },
                }

                # Feed the reviewer's answer back to the LLM.
                merged = {
                    **cleaned,
                    "human_reviewed": True,
                    "reviewer_decision": {
                        "relevance": reviewer_row.relevance,
                        "privilege": reviewer_row.privilege,
                        "confidence": reviewer_row.confidence,
                    },
                    "reviewer_notes": override.get("reviewer_notes") or "",
                }
                messages.append(_tool_result_message(block.id, merged))
            else:
                # Confidence at or above floor: agent's proposal stands.
                proposed_this_batch += 1
                yield {
                    "type": "document_decision_proposed",
                    "data": {
                        "doc_id": doc_id,
                        "decision_id": cleaned.get("decision_id"),
                        "relevance": cleaned.get("relevant"),
                        "privilege": cleaned.get("privilege"),
                        "confidence": cleaned.get("confidence"),
                        "proposed_by": "agent",
                    },
                }
                messages.append(_tool_result_message(block.id, cleaned))

            if proposed_this_batch >= run.batch_size:
                yield {
                    "type": "batch_complete",
                    "data": {"proposed": proposed_this_batch, "reason": "batch_size_reached"},
                }
                return
            continue

        # ---- LLM voluntary request_human_review — write reviewer Decision & count ---- #
        if (
            block.name == "request_human_review"
            and isinstance(cleaned, dict)
            and "error" not in cleaned
        ):
            doc_id = arguments.get("doc_id")
            r_decision = cleaned.get("decision") or {}
            if r_decision:
                reviewer_row = Decision.objects.create(
                    run_id_id=run_id,
                    doc_id_id=doc_id,
                    proposed_by="reviewer",
                    relevance=bool(r_decision.get("relevance", False)),
                    privilege=r_decision.get("privilege", "unclear"),
                    issue_tags=r_decision.get("issue_tags", []),
                    confidence=float(r_decision.get("confidence", 1.0)),
                    reasoning=(
                        cleaned.get("reviewer_notes") or r_decision.get("reasoning") or ""
                    )[:8000],
                    committed=False,
                )
                proposed_this_batch += 1
                yield {
                    "type": "document_decision_proposed",
                    "data": {
                        "doc_id": doc_id,
                        "decision_id": reviewer_row.decision_id,
                        "relevance": reviewer_row.relevance,
                        "privilege": reviewer_row.privilege,
                        "confidence": reviewer_row.confidence,
                        "proposed_by": "reviewer",
                        "reviewer_notes": cleaned.get("reviewer_notes") or "",
                    },
                }
                if proposed_this_batch >= run.batch_size:
                    messages.append(_tool_result_message(block.id, cleaned))
                    yield {
                        "type": "batch_complete",
                        "data": {"proposed": proposed_this_batch, "reason": "batch_size_reached"},
                    }
                    return

            messages.append(_tool_result_message(block.id, cleaned))
            continue

        # ---- Every other tool: feed the result back and keep looping ---- #
        messages.append(_tool_result_message(block.id, cleaned))

    # Fell off the iteration cap.
    yield {
        "type": "run_paused",
        "data": {"reason": "iteration_cap", "proposed": proposed_this_batch},
    }
