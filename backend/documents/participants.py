"""
Participant address resolution for EDRM Enron v2 base emails (spec §5).

Pure functions, no Django dependency. Consumed by:
- documents.parsing                                    (ingest-time resolution — Task 7)
- documents.management.commands.backfill_participants  (one-time DB backfill)
- agent.tools.read.read_document                       (returns the resolved units)

Replaces the earlier `split_participants` / `extract_sender_display` in parsing.py,
which the format survey proved defective on ~1,580 documents (case-sensitive `</O=`
marker missing lowercase `</o=`; the `Last, First <addr>` comma trap; and bare-comma
addresses merged beside an X.500 unit).

TWO FUNCTIONS
- resolve_field(value): split a raw To:/From:/Cc: header VALUE into participant units,
  correctly, then resolve each. This is the corrected splitter + resolver in one.
- resolve_unit(raw):    classify one already-isolated participant string into a
  structured unit {raw, display, kind, cn_code, email, domain}.

STRUCTURED UNIT SHAPE
    {
      "raw":     canonicalised single-unit substring (whitespace between display and
                 bracket collapsed to one space; trailing separator dropped). NOT
                 byte-for-byte verbatim — for the pristine header text, read
                 Document.raw_headers.
      "display": the label to show a reviewer / hand the agent,
      "kind":    one of the survey categories (below),
      "cn_code": Exchange CN code, or None,
      "email":   email address, or None,
      "domain":  email domain (lowercased), or None,
    }

KINDS and their display tier:
  resolved-name   : x500_named | smtp_prefixed | bare_name   -> display is a human label
  address-only    : smtp_internal | smtp_external           -> display is the email
  unresolved      : x500_blank | other                      -> display is "(Unresolved)"
`kind` implies the tier, so the UI can render names normally and grey out
"(Unresolved)" without a separate flag.
"""

from __future__ import annotations

import re

UNRESOLVED = "(Unresolved)"

# An email token: an '@'-bearing run with no whitespace, brackets, commas, semicolons,
# or quotes. Deliberately permissive on the local part (this corpus has messy tokens).
_EMAIL_RE = re.compile(r"[^\s<>,;\"']+@[^\s<>,;\"']+")

# CN=<code> fragments inside an X.500 DN. We take the LAST one (the person code;
# earlier CNs are container names like RECIPIENTS / Notesaddr). Case-insensitive.
_CN_RE = re.compile(r"[Cc][Nn]=([^/>,\s]+)")


def _clean(s: str) -> str:
    """Trim whitespace and surrounding quotes from a raw fragment."""
    return s.strip().strip("\"'").strip()


def _email_and_domain(text: str) -> tuple[str | None, str | None]:
    m = _EMAIL_RE.search(text)
    if not m:
        return None, None
    email = m.group(0).strip("\"'.,;>")
    domain = email.rsplit("@", 1)[-1].lower().strip(" >\"'.,;") if "@" in email else None
    return email, (domain or None)


def resolve_unit(raw: str) -> dict:
    """Classify a single, already-isolated participant string into a structured unit."""
    raw = (raw or "").strip()
    unit = {"raw": raw, "display": None, "kind": None,
            "cn_code": None, "email": None, "domain": None}

    if not raw:
        unit["kind"], unit["display"] = "other", UNRESOLVED
        return unit

    lt, gt = raw.find("<"), raw.rfind(">")
    has_bracket = lt != -1 and gt != -1 and gt > lt

    if has_bracket:
        prefix = _clean(raw[:lt])
        inner = raw[lt + 1:gt].strip()
        inner_low = inner.lower()

        if "@" in inner:
            # Email-bearing bracket => prefixed SMTP (incl. IMCEAEX proxies, which
            # carry both '@' and CN= but are a single real recipient — '@' wins).
            email, domain = _email_and_domain(inner)
            unit.update(kind="smtp_prefixed", email=email, domain=domain,
                        display=prefix or email or UNRESOLVED)
        elif "cn=" in inner_low:
            # X.500 distinguished name (no '@').
            cn = _CN_RE.findall(inner)
            unit["cn_code"] = cn[-1] if cn else None
            if prefix:
                unit.update(kind="x500_named", display=prefix)
            else:
                unit.update(kind="x500_blank", display=UNRESOLVED)
        else:
            # Junk bracket: <>, <.>, <label:;>, source-truncated fragments.
            unit.update(kind="other", display=prefix or UNRESOLVED)
        return unit

    # No usable bracket.
    if "@" in raw:
        email, domain = _email_and_domain(raw)
        internal = bool(domain) and domain.endswith("enron.com")
        unit.update(kind="smtp_internal" if internal else "smtp_external",
                    email=email, domain=domain, display=email or _clean(raw))
    else:
        unit.update(kind="bare_name", display=_clean(raw))
    return unit

# ------------------------- Name matching -------------------------
# Shared token-subset matcher, used by check_privilege_signals (lawyer display
# matching) and the scoped-retrieval tool (name search). Robust to "Last, First" vs
# "First Last" ordering and to middle initials.

# Units whose kind gives us something to match a person against (i.e. not
# x500_blank / other). Used for the participants_unresolved determination too.
MATCHABLE_KINDS = frozenset(
    {"x500_named", "smtp_prefixed", "smtp_internal", "smtp_external", "bare_name"}
)


def name_tokens(s: str) -> set[str]:
    """Lowercased alphanumeric tokens of a name/display string."""
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def token_subset_match(query: str, target: str) -> bool:
    """True when every token of `query` appears in `target` (order-independent).

    Directional on purpose: use the canonical/shorter name as `query` (e.g. a lawyer
    display-variant) and the observed participant display as `target`, so "Sara
    Shackleton" matches "Shackleton, Sara M." but a bare "Shackleton" does not match the
    full "Sara Shackleton" (avoids surname-only false hits on common surnames)."""
    q = name_tokens(query)
    return bool(q) and q <= name_tokens(target)


def resolve_field(value: str | None) -> list[dict]:
    """Split a raw To:/From:/Cc: VALUE into participant units and resolve each.

    Corrected splitter: instead of guessing a whole-field delimiter (the old bug),
    anchor on angle brackets, which are unambiguous — a `<...>` group never contains a
    separator in this corpus. For each bracket, everything since the previous unit is
    its prefix; complete email tokens are peeled off the FRONT of that prefix as their
    own units, and the trailing non-email run (which may legitimately contain the comma
    in "Last, First") becomes the bracket's display name.

    KNOWN LIMITATION — over-splits bare "Last, First" units. A bracketless "Last, First"
    (either the whole field, or one participant in a comma list with no `<...>` anywhere
    to anchor on) splits into "Last" + "First" bare-name units. Impact is bounded but
    real: token_subset_match(query="Last, First", target="Last") is FALSE — every query
    token must appear in the target — so a lawyer whose canonical variant is "Sanders,
    Richard" is MISSED when the observed unit is bare "Sanders" alone. The impact is
    bounded because Enron in-house counsel almost always appear as X.500 or SMTP (where
    the bracket anchors and the display prefix stays intact), not as bare "Last, First".
    Callers with a SINGLE-participant field (From: is always one participant) should use
    resolve_unit() directly, which keeps "Last, First" intact — resolve_field is for
    the multi-participant To:/Cc: path.
    """
    if not value or not value.strip():
        return []
    value = value.strip()
    units: list[dict] = []
    i, n = 0, len(value)

    while i < n:
        lt = value.find("<", i)
        if lt == -1:
            # Tail with no bracket: plain comma-split into bare units.
            for seg in value[i:].split(","):
                if seg.strip():
                    units.append(resolve_unit(seg))
            break

        gt = value.find(">", lt)
        if gt == -1:
            # Unterminated bracket (source-truncated): take the rest as one unit.
            units.append(resolve_unit(value[i:]))
            break

        prefix = value[i:lt]
        bracket = value[lt:gt + 1]

        # Peel complete email segments off the FRONT; the trailing non-email run is
        # this bracket's display name (this is what fixes the "Last, First" trap).
        segs = prefix.split(",")
        display_segs: list[str] = []
        while segs and "@" not in segs[-1]:
            display_segs.insert(0, segs.pop())
        for seg in segs:
            if seg.strip():
                units.append(resolve_unit(seg))

        # Join non-empty display segments; ", " keeps a real "Last, First" intact
        # while dropping the stray trailing comma/space that separated it from the bracket.
        display_prefix = ", ".join(s.strip() for s in display_segs if s.strip())
        unit_str = f"{display_prefix} {bracket}".strip() if display_prefix else bracket
        units.append(resolve_unit(unit_str))

        i = gt + 1
        while i < n and value[i] in ", \t":
            i += 1

    return units