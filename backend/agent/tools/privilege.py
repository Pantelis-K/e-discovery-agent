"""
check_privilege_signals tool (spec §3) — deterministic, auditable privilege triage.

DETERMINISTIC BY DESIGN, NOT LLM (§3). The point of this tool is that a privilege
flag can be explained to an auditor as a structured signal set ("Shackleton in From,
'attorney work product' in body"), never "the LLM said so". The orchestrator LLM
interprets these signals into a proposed decision; the signals themselves are rules.

Computes ALL signals live at call time from the document (participants + body):
  * participant signals - match the RESOLVED participant units (read_document's
    from_display/to_display/cc_display, produced by documents.participants) against the
    lawyer list STRUCTURALLY: exact cn_code, exact email (high confidence), or a
    token-subset display match (lower confidence - surname collisions). Each match is
    recorded as {name, via, matched} for audit. Unresolved unless BOTH From and To
    carry a matchable participant - do NOT read "no lawyer found" as "not privileged"
    (§3/§5).
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
from documents.participants import MATCHABLE_KINDS, token_subset_match

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


def _match_lawyer(unit: dict) -> dict | None:
    """Best lawyer match for one resolved participant unit, or None.

    Matches STRUCTURALLY on the resolved unit's fields (not a substring scan of raw
    text — that was what the mis-splits broke). Precedence, high confidence first:
      1. cn_code  — exact, case-insensitive (an Exchange CN code is a person key)
      2. email    — exact, case-insensitive
      3. display  — token-subset against a lawyer display-variant (lower confidence:
                    surname collisions exist, e.g. Tana Jones vs Karen Jones)
    Exact (cn/email) wins over display across ALL lawyers, so the two passes are
    separated. Returns {name, via, matched} for an auditable signal ("Shackleton via
    cn_code=Sshackl in From") rather than an opaque name."""
    cn = (unit.get("cn_code") or "").lower()
    email = (unit.get("email") or "").lower()
    display = unit.get("display") or ""

    for lawyer in LAWYERS:
        if cn and any(cn == c.lower() for c in lawyer.get("cn_codes", [])):
            return {"name": lawyer["name"], "via": "cn_code", "matched": unit["cn_code"]}
        if email and any(email == e.lower() for e in lawyer.get("emails", [])):
            return {"name": lawyer["name"], "via": "email", "matched": unit["email"]}
    for lawyer in LAWYERS:
        if display and any(token_subset_match(v, display)
                           for v in lawyer.get("display_variants", [])):
            return {"name": lawyer["name"], "via": "display", "matched": display}
    return None


def _match_field(units: list[dict]) -> tuple[list[dict], list[str]]:
    """(lawyer match dicts, external-counsel domains) for one field's resolved units.
    Deduplicates lawyers by name within the field, keeping the first (highest-confidence)
    match seen."""
    matches: list[dict] = []
    seen: set[str] = set()
    domains: list[str] = []
    for unit in units:
        m = _match_lawyer(unit)
        if m and m["name"] not in seen:
            matches.append(m)
            seen.add(m["name"])
        dom = (unit.get("domain") or "").lower()
        if dom:
            for d in EXTERNAL_COUNSEL_DOMAINS:
                if d.lower() in dom:
                    domains.append(d)
    return matches, sorted(set(domains))


def _field_usable(units: list[dict]) -> bool:
    """True if the field carries at least one matchable participant (present AND not
    all x500_blank/other). Drives participants_unresolved."""
    return any(u.get("kind") in MATCHABLE_KINDS for u in units)


def _scan_content(body: str) -> tuple[bool, bool, list[str]]:
    low = (body or "").lower()
    conf = [p for p in CONFIDENTIALITY_PATTERNS if p in low]
    legal = [p for p in LEGAL_ADVICE_PATTERNS if p in low]
    return bool(conf), bool(legal), conf + legal


def _detect_forwarded(body: str) -> bool:
    low = (body or "").lower()
    return any(m in low for m in FORWARD_MARKERS)


def _strength(high_conf_lawyer: bool, display_only_lawyer: bool,
              external_present: bool, has_conf: bool, has_legal: bool) -> str:
    """Content-weighted aggregate (§3) - a hint, not a decision.

    A TRUSTWORTHY participant signal is a high-confidence lawyer match (cn_code/email)
    or an external-counsel domain. A display-ONLY lawyer match is collision-prone
    (common surnames), so on its own it counts only as a weak signal.
    none    : nothing
    weak    : one content signal, or a display-only lawyer match, with no trustworthy participant
    moderate: two content signals; or a trustworthy participant (alone or + one content)
    strong  : trustworthy participant + two content signals, or lawyer AND external + content
    """
    participant = high_conf_lawyer or external_present
    content = int(has_conf) + int(has_legal)
    if not participant:
        if content >= 2:
            return "moderate"
        if content == 1 or display_only_lawyer:
            return "weak"
        return "none"
    if content == 0:
        return "moderate"
    if content >= 2 or (high_conf_lawyer and external_present):
        return "strong"
    return "moderate"


def _compute_signals(from_units, to_units, cc_units, body) -> dict:
    """Pure signal computation over RESOLVED participant units - no DB, unit-testable.
    from_units/to_units/cc_units are lists of the structured units produced by
    documents.participants (from read_document's *_display fields)."""
    from_units = from_units or []
    to_units = to_units or []
    cc_units = cc_units or []

    from_matches, from_domains = _match_field(from_units)
    to_matches, to_domains = _match_field(to_units)
    cc_matches, cc_domains = _match_field(cc_units)
    external_domains = sorted(set(from_domains + to_domains + cc_domains))

    has_conf, has_legal, matched = _scan_content(body)

    all_matches = from_matches + to_matches + cc_matches
    high_conf_lawyer = any(m["via"] in ("cn_code", "email") for m in all_matches)
    display_only_lawyer = any(m["via"] == "display" for m in all_matches)

    # §3 (refined): unresolved unless BOTH From and To carry at least one matchable
    # participant. A field that is missing, or present but all x500_blank/other, is not
    # usable. Conservative by design - "no lawyer found" must not read as "not privileged".
    participants_unresolved = not (_field_usable(from_units) and _field_usable(to_units))

    return {
        "participant_signals": {
            # Each entry: {name, via: cn_code|email|display, matched: <value>} (§3).
            "known_lawyers_in_from": from_matches,
            "known_lawyers_in_to": to_matches,
            "known_lawyers_in_cc": cc_matches,
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
            high_conf_lawyer, display_only_lawyer, bool(external_domains),
            has_conf, has_legal,
        ),
    }


def check_privilege_signals(doc_id: str) -> dict:
    from agent.tools.read import read_document   # lazy: keeps module import Django-free

    doc = read_document(doc_id)
    if "error" in doc:
        return {"error": f"privilege: cannot read document - {doc['error']}"}

    # Match on the RESOLVED participant units (from_display is one unit or None;
    # to_/cc_display are lists), not the raw strings (spec §5 identity resolution).
    from_unit = doc.get("from_display")
    return _compute_signals(
        [from_unit] if from_unit else [],
        doc.get("to_display") or [],
        doc.get("cc_display") or [],
        doc.get("body"),
    )