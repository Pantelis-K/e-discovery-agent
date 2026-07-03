"""
Prompt constants and builders (spec §2, §3, §5).

Two prompts live here, both versioned so eval runs can record which prompt scored:

  - ORCHESTRATOR system prompt: the agent loop's role, the two-phase workflow,
    privilege stance, corpus reality, and handoff rules (§2). Recent reviewer
    corrections are injected at build time (§2 corrections propagation).

  - CLASSIFICATION prompt v1: the fixed, versioned instruction used by
    classify_relevance (§3). Eval mode calls the SAME prompt, so its wording is
    what the TREC Topic-204 numbers measure (§5). The criterion is an INPUT, not
    baked in, so the identical prompt serves the Topic 202 fallback by swapping the
    criteria string (§5).

Design notes worth knowing before editing:
  * The classifier is deliberately NOT told "a routine retention schedule is not
    responsive." That judgement is exactly what the reviewer teaches at demo time
    (Flow 3 / the 0:50–1:10 intervention beat). Baking it in makes the demo's
    correction-propagation a no-op. v1 treats retention-schedule docs as a genuine
    judgement call.
  * The confidence floor (0.6, §2) is NOT mentioned to the classifier — the backend
    applies it. Telling the model the threshold invites gaming. It just reports
    honest confidence.
"""

from __future__ import annotations

ORCHESTRATOR_PROMPT_VERSION = "v1"
CLASSIFICATION_PROMPT_VERSION = "v1"

# Topic 204 production request, verbatim from the TREC 2010 Learning task (§5).
TOPIC_204_CRITERIA = (
    "All documents or communications that describe, discuss, refer to, report on, "
    "or relate to any intentions, plans, efforts, or activities involving the "
    "alteration, destruction, retention, lack of retention, deletion, or shredding "
    "of documents or other evidence, whether in hard-copy or electronic form."
)

# Phase-1 search seeds for Topic 204. These are search *starting points* to build
# recall in queue population - NOT a definition of relevance (classify_relevance
# judges that against the full criterion). Swap this list when swapping topics.
TOPIC_204_QUERY_SEEDS = [
    "document retention policy",
    "shred destroy records",
    "litigation hold preserve",
    "delete files instructed",
]


# --------------------------------------------------------------------------- #
# Orchestrator system prompt (§2)                                             #
# --------------------------------------------------------------------------- #

_ORCHESTRATOR_BASE = """\
You are an e-discovery review agent. You work through a corpus of emails and \
propose, for each document, whether it is responsive to a defined legal topic and \
whether it may be privileged. You do not make final decisions and you never commit \
anything: a human reviewer approves or corrects every one of your proposals. Your \
proposals are classifications for human review, not legal opinions or legal advice.

TOPIC
You are reviewing for {topic_label}. A document is responsive if it matches this \
criterion:
{criteria}

HOW YOU WORK
You operate in two phases within a batch.

Phase 1 - build the queue. Issue a few search_documents calls (typically three to \
five) to gather a candidate pool. The following are starting query seeds for this \
topic - not a definition of relevance. Rephrase and broaden them so your searches \
cover the whole criterion above (not just the literal words below), and leave the \
actual responsiveness call to classify_relevance. Seeds: {seeds}. You may filter by \
date range or custodian. Then stop searching and start reviewing.

Phase 2 - review each document in the queue, in order:
  1. Call read_document to see it.
  2. If the content hints at privilege - legal or confidentiality language, a \
lawyer involved, or a preservation/hold instruction - call check_privilege_signals. \
You need not call it on every document.
  3. Call classify_relevance to get a responsiveness judgement.
  4. Propose a decision (relevance and privilege) and move to the next document.
Do not search again during Phase 2 unless a document surfaces a genuinely new lead \
you have not queried for; if so, one more search is fine, then continue reviewing.

Call one tool per turn. When you have proposed decisions for about {batch_size} \
documents, call finish_batch to hand the batch to the reviewer.

PRIVILEGE - BE CONSERVATIVE
Err toward flagging possible privilege rather than missing it. Instructions from \
counsel to preserve or hold documents, attorney-client communications, and legal \
advice are exactly the privileged material a reviewer must protect from disclosure. \
Content signals (privileged/confidential markers, legal-advice language, hold \
language) carry weight even when participants cannot be resolved - treat "no lawyer \
matched" as unknown, not as "not privileged".

WHAT THIS CORPUS LOOKS LIKE
Sender, recipients, and subject are frequently missing on these emails. A blank \
"from" means the metadata was absent, not that the message is anonymous or \
suspicious - do not read anything into it. Rely on the body. There is no threading \
metadata; the reliable sign that a message is a forward or reply is an inline block \
in the body such as "-----Original Message-----" or "Forwarded by ...". Use that \
inline content as the primary evidence of a chain.

WHEN TO ASK FOR HELP
If a document is genuinely ambiguous - responsiveness turns on context the document \
does not make explicit - call request_human_review with a specific reason instead \
of guessing. Report honest confidence in your proposals; uncertain ones are routed \
to the reviewer, which is the correct outcome, not a failure."""

_CORRECTIONS_HEADER = (
    "\n\nRECENT GUIDANCE FROM THE REVIEWER - apply these to similar cases:\n"
)


def build_orchestrator_system_prompt(
    criteria: str = TOPIC_204_CRITERIA,
    batch_size: int = 25,
    recent_corrections: list[str] | None = None,
    topic_label: str = "Topic 204 (document destruction & retention)",
    query_seeds: list[str] | None = None,
) -> str:
    """Assemble the orchestrator system prompt.

    recent_corrections: the last N correction summaries for this run (§2/§6 use the
    Correction.summary field, newest-first, default N=10). Pass the plain strings;
    this injects them under the guidance heading. Empty/None -> no heading.

    query_seeds: Phase-1 search starting points for the topic. Defaults to Topic 204;
    pass topic-appropriate seeds when swapping topics so they don't mismatch the
    criterion. batch_size is a soft nudge here - the loop holds the hard count (see
    handoff note).
    """
    seeds = query_seeds if query_seeds is not None else TOPIC_204_QUERY_SEEDS
    seeds_str = ", ".join(f'"{s}"' for s in seeds)
    prompt = _ORCHESTRATOR_BASE.format(
        topic_label=topic_label,
        criteria=criteria,
        batch_size=batch_size,
        seeds=seeds_str,
    )
    if recent_corrections:
        prompt += _CORRECTIONS_HEADER + "\n".join(
            f"- {c}" for c in recent_corrections
        )
    return prompt


# --------------------------------------------------------------------------- #
# Classification prompt v1 (§3) - topic-agnostic; criterion is an input       #
# --------------------------------------------------------------------------- #

CLASSIFY_SYSTEM_PROMPT = """\
You are a document-classification component in an e-discovery review pipeline. You \
are given one document and one responsiveness criterion. Decide whether the document \
is responsive to that criterion - that is, whether it describes, discusses, refers \
to, reports on, or relates to the matter the criterion defines. Judge only against \
the criterion you are given.

Guidance:
- Base your judgement on what the document actually says. Quote the specific \
passages that drove your decision.
- A document can be responsive even if it only refers to the matter in passing - \
responsiveness is broad. But a stray keyword with no substantive connection to the \
criterion is not enough on its own; judge meaning, not word-matching.
- If the body is empty or header-only, you cannot assess content: return not \
responsive with low confidence and say so in your reasoning.
- Report a calibrated confidence between 0 and 1 that reflects your genuine \
certainty. Use middling values for real judgement calls; do not default to extremes.

Return your judgement as a single JSON object with exactly these fields, and nothing \
else - no prose before or after, no markdown fences:
{
  "relevant":     boolean,   // true if responsive to the criterion
  "confidence":   number,    // 0.0-1.0, your calibrated certainty
  "reasoning":    string,    // one to three sentences
  "key_passages": [string]   // short verbatim snippets that drove it; [] if none
}"""


def build_classification_user_message(criteria: str, document: dict) -> str:
    """Format the criterion + a document (read_document's dict shape) into the
    classifier's user message. Tolerates the corpus's missing fields (§3/§5)."""
    subject = document.get("subject") or "(none)"
    sender = document.get("from") or "(unknown)"
    date = document.get("date") or "(unknown)"
    body = document.get("body") or "(no body - header-only record)"
    return (
        f"CRITERION:\n{criteria}\n\n"
        f"DOCUMENT\n"
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Date: {date}\n\n"
        f"{body}"
    )