"""
classify_relevance tool (spec §3) - the one tool that calls the Anthropic API.

Given a doc_id and a responsiveness criterion, returns a RelevanceJudgment:
  {relevant: bool, confidence: float, reasoning: str, key_passages: [str]}

Design (see the prompts.py handoff):
  * Structured output via a FORCED tool call (`record_judgment`) rather than parsing
    JSON out of free text: the model must emit a tool_use block whose .input is
    already a dict, so there is no fence-stripping and no malformed-JSON retry path.
    This is our reading of the §3 "malformed output -> retry, then error" line -
    forced tool use enforces the shape up front instead.
  * Haiku always (§2 cost strategy #2). temperature 0 for reproducible eval scoring.
  * Body truncated to ~6,000 chars before the call (§2 eval note); logged when it
    fires. Truncation lives HERE, not only in run_eval, so the cockpit and eval mode
    classify identically - eval scores this exact tool, so the paths must not diverge.
  * Prompt v1 is topic-agnostic; the criterion arrives via the user message, so the
    same tool serves the Topic 202 fallback by swapping the criteria string (§5).

The Anthropic client is created lazily (not at import time) so that importing
agent.tools - which pulls this module in via tools/__init__.py - does NOT require
ANTHROPIC_API_KEY to be set. Otherwise migrations and the read_document shell test
would fail to import the package. (loop.py currently instantiates its client at
module level - same latent issue; see handoff.)

Returns {"error": str} on any failure, matching the other tools, so the loop can
hand the orchestrator a tool_result it can course-correct on (§2 failure modes).
"""

from __future__ import annotations

import logging
import random
import time

import anthropic

from agent.prompts import CLASSIFY_SYSTEM_PROMPT, build_classification_user_message
from agent.tools.read import read_document

logger = logging.getLogger(__name__)

# Haiku always (§2). One-line change if a different Haiku build is preferred;
# kept consistent with the model string already used in loop.py.
CLASSIFIER_MODEL = "claude-3-5-haiku-latest"
MAX_OUTPUT_TOKENS = 1024
MAX_BODY_CHARS = 6000            # §2 eval truncation

# Rate-limit backoff (§2: exponential backoff on 429s; eval makes thousands of calls).
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2.0

RECORD_JUDGMENT_TOOL = {
    "name": "record_judgment",
    "description": "Record the responsiveness judgment for the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevant": {
                "type": "boolean",
                "description": "true if the document is responsive to the criterion",
            },
            "confidence": {
                "type": "number",
                "description": "calibrated certainty from 0.0 to 1.0",
            },
            "reasoning": {
                "type": "string",
                "description": "one to three sentences explaining the judgment",
            },
            "key_passages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "short verbatim snippets that drove the decision; [] if none",
            },
        },
        "required": ["relevant", "confidence", "reasoning", "key_passages"],
    },
}

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
                raise                       # non-retryable (400/401/403/404/...)
            last_exc, reason = e, "overloaded_529"
        if attempt >= MAX_RETRIES:
            raise last_exc
        sleep_for = delay + random.uniform(0, delay * 0.25)
        logger.warning(
            "classify: %s - retry %d/%d in %.1fs", reason, attempt + 1, MAX_RETRIES, sleep_for
        )
        time.sleep(sleep_for)
        delay *= 2
    raise last_exc  # unreachable; satisfies type-checkers


def _clamp_confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    return []


def classify_relevance(doc_id: str, criteria: str) -> dict:
    if not criteria:
        # Defensive: dispatch passes args["criteria"]; empty means a caller bug.
        return {"error": "classify: no criteria provided"}

    doc = read_document(doc_id)
    if "error" in doc:
        return {"error": f"classify: cannot read document - {doc['error']}"}

    body = doc.get("body") or ""
    if len(body) > MAX_BODY_CHARS:
        logger.info(
            "classify: truncating body of %s (%d -> %d chars)",
            doc_id, len(body), MAX_BODY_CHARS,
        )
        doc = {**doc, "body": body[:MAX_BODY_CHARS]}

    user_message = build_classification_user_message(criteria, doc)

    try:
        response = _messages_with_backoff(
            model=CLASSIFIER_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0,
            system=CLASSIFY_SYSTEM_PROMPT,
            tools=[RECORD_JUDGMENT_TOOL],
            tool_choice={"type": "tool", "name": "record_judgment"},
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        logger.error("classify: API error for %s: %s", doc_id, e)
        return {"error": f"classify: API error - {e}"}

    tool_blocks = [b for b in response.content if b.type == "tool_use"]
    if not tool_blocks:
        # Forced tool_choice makes this near-impossible; treat as a hard error.
        return {"error": "classify: model returned no judgment"}

    judgment = tool_blocks[0].input or {}
    return {
        # Echo doc_id so the orchestrator has a fresh copy on every turn — helps
        # Haiku not lose the doc_id across the read → priv → classify → propose flow.
        "doc_id": doc_id,
        "relevant": bool(judgment.get("relevant", False)),
        "confidence": _clamp_confidence(judgment.get("confidence")),
        "reasoning": str(judgment.get("reasoning", "")),
        "key_passages": _as_str_list(judgment.get("key_passages")),
        # Internal telemetry (§2 token tracking). Callers read this: the loop folds it
        # into agent_steps.tokens_*, eval sums it for the pilot cost. STRIP it before
        # putting the result in the orchestrator's tool_result. Harmless if left in.
        "_usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }