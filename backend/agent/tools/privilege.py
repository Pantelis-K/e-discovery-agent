"""
check_privilege_signals tool (spec §3) — deterministic, auditable privilege triage.

DETERMINISTIC BY DESIGN, NOT LLM (§3). The point of this tool is that a privilege
flag can be explained to an auditor as a structured signal set ("Shackleton in From,
'attorney work product' in body"), never "the LLM said so". The orchestrator LLM
interprets these signals into a proposed decision; the signals themselves are rules.

Computes ALL signals live at call time from the document (participants + body):
  * participant signals - match From/To/Cc against the lawyer list (agent/lawyers.py)
    on any of three keys: SMTP email, X.500 CN code, or display name (§5). Absent
    From/To -> participants_unresolved (do NOT read "no lawyer found" as "not
    privileged" - §3).
  * content signals - case-insensitive phrase scan of the body (confidentiality /
    privilege markers; legal-advice and Topic-204 preservation/hold language, §3).
  * context signals - is_forwarded from inline body markers (the reliable forward
    signal now that find_thread is cut, §3); thread_confidence is always "low"
    (threading is heuristic/unreliable in this corpus).
  * overall_signal_strength - a content-weighted rules aggregate (§3), a HINT to the
    LLM, not a decision.

DIVERGENCE (flagged for Architecture). §3/§6 envisioned participant signals
precomputed at ingestion into a `privilege_signals` cache table. That model does not
exist and ingestion does not populate it. This tool computes everything live instead;
it is millisecond-cheap on one document, so the cache is an unneeded optimization at
demo scale. If the cache is ever built, this exact logic is what it would run.

Errors: doc not found -> {"error": ...}. Missing participant metadata is NOT an error
- it degrades to empty participant signals with participants_unresolved=True (§3).
"""

from __future__ import annotations

from agent.lawyers import LAWYERS, EXTERNAL_COUNSEL_DOMAINS

# --- content phrase banks (lowercase; matched as substrings of the body) ----------

CONFIDENTIALITY_PATTERNS = [
    "privileged and confidential",
    "privileged & confidential",
    "confidential and privileged",
    "attorney-client privilege",       # also catches "...privileged"
    "attorney client privilege",
    "attorney work product",
]

LEGAL_ADVICE_PATTERNS = [
    "legal advice",
    "seeking legal advice",
    "advice of counsel",
    "consult counsel",
    "consult with counsel",
    # Topic-204 preservation / hold language (§3) - legal-process instructions
    "litigation hold",
    "legal hold",
    "preservation notice",
    "preservation obligation",
    "preserve all documents",
    "do not delete",
    "do not destroy",
    "retention notice",
]

FORWARD_MARKERS = [
    "-----original message-----",
    "forwarded by",
    "---------------------- forwarded",
]


def _match_participants(participants: list[str]) -> tuple[list[str], list[str]]:
    """(matched lawyer names, matched external-counsel domains) for raw participant
    strings. Case-insensitive substring on any lawyer key handles all three §5 forms."""
    names: list[str] = []
    domains: list[str] = []
    for raw in participants:
        if not raw:
            continue
        low = raw.lower()
        for lawyer in LAWYERS:
            keys = (
                lawyer.get("emails", [])
                + lawyer.get("display_variants", [])
                + lawyer.get("cn_codes", [])
            )
            if any(k and k.lower() in low for k in keys):
                names.append(lawyer["name"])
                break
        if "@" in low:
            domain = low.rsplit("@", 1)[-1].strip(" >\"'")
            for d in EXTERNAL_COUNSEL_DOMAINS:
                if d.lower() in domain:
                    domains.append(d)
    return sorted(set(names)), sorted(set(domains))


def _scan_content(body: str) -> tuple[bool, bool, list[str]]:
    low = (body or "").lower()
    conf = [p for p in CONFIDENTIALITY_PATTERNS if p in low]
    legal = [p for p in LEGAL_ADVICE_PATTERNS if p in low]
    return bool(conf), bool(legal), conf + legal


def _detect_forwarded(body: str) -> bool:
    low = (body or "").lower()
    return any(m in low for m in FORWARD_MARKERS)


def _strength(lawyer_present: bool, external_present: bool,
              has_conf: bool, has_legal: bool) -> str:
    """Content-weighted aggregate (§3) - a hint, not a decision.
    none    : nothing
    weak    : a single content signal, no participant signal (content-only, §3)
    moderate: participant alone; participant + one content; or two content signals
              with no participant (content-weighted for §5 participant gaps)
    strong  : participant + two content signals, or lawyer AND external counsel with
              content (multiple signals, §3)
    """
    participant = lawyer_present or external_present
    content = int(has_conf) + int(has_legal)
    if content == 0 and not participant:
        return "none"
    if not participant:
        return "weak" if content == 1 else "moderate"
    if content == 0:
        return "moderate"
    if content >= 2 or (lawyer_present and external_present):
        return "strong"
    return "moderate"


def _compute_signals(from_addr, to_list, cc_list, body) -> dict:
    """Pure signal computation - no DB, unit-testable in isolation."""
    to_list = to_list or []
    cc_list = cc_list or []
    from_participants = [from_addr] if from_addr else []

    from_names, from_domains = _match_participants(from_participants)
    to_names, to_domains = _match_participants(to_list)
    cc_names, cc_domains = _match_participants(cc_list)
    external_domains = sorted(set(from_domains + to_domains + cc_domains))

    has_conf, has_legal, matched = _scan_content(body)
    lawyer_present = bool(from_names or to_names or cc_names)
    # §3: flag true when we lack the participant metadata to judge - i.e. no From/To.
    participants_unresolved = not (bool(from_addr) or bool(to_list))

    return {
        "participant_signals": {
            "known_lawyers_in_from": from_names,
            "known_lawyers_in_to": to_names,
            "known_lawyers_in_cc": cc_names,
            "external_counsel_domains": external_domains,
            "participants_unresolved": participants_unresolved,
        },
        "content_signals": {
            "has_confidentiality_marker": has_conf,
            "has_legal_advice_language": has_legal,
            "matched_phrases": matched,
        },
        "context_signals": {
            "is_forwarded": _detect_forwarded(body),
            "thread_confidence": "low",   # threading unreliable; find_thread cut (§3)
        },
        "overall_signal_strength": _strength(
            lawyer_present, bool(external_domains), has_conf, has_legal
        ),
    }


def check_privilege_signals(doc_id: str) -> dict:
    from agent.tools.read import read_document   # lazy: keeps module import Django-free

    doc = read_document(doc_id)
    if "error" in doc:
        return {"error": f"privilege: cannot read document - {doc['error']}"}

    return _compute_signals(
        doc.get("from"), doc.get("to"), doc.get("cc"), doc.get("body")
    )