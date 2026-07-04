"""
Hardcoded lawyer / counsel list for check_privilege_signals (spec §3, §5).

WHY HARDCODED, WHY THREE KEYS. Internal Enron participants appear in three
inconsistent forms (§5): clean SMTP (name@enron.com), Exchange X.500 DN
(`Name </O=ENRON/OU=.../CN=RECIPIENTS/CN=CODE>`), and bare display name. There is NO
directory in the corpus and NO @enron.com address for an X.500-addressed person — a
CN code resolves only to a display name. So each lawyer carries ALL THREE keys and
participant matching (privilege.py) succeeds on whichever form appears.

STATUS: 
MATCHING (privilege.py, structural — not substring). Each resolved participant unit is
matched against these keys: exact `cn_codes` / `emails` (high confidence) or a
token-subset match of the unit display against `display_variants` (lower confidence,
surname-collision-prone). So partial data still matches on SMTP + display name; filling
`cn_codes` improves X.500 coverage and confidence.

STATUS: STARTER FIXTURE — complete against the corpus before privilege matching is
trustworthy. Names/roles are the §5 lawyer-custodians. `emails` follow Enron's
firstname.lastname@enron.com convention and MUST be verified (Chat C).
`display_variants` are the predictable "Last, First" / "First Last" forms —
`token_subset_match` handles middle initials and role suffixes ("Taylor, Mark E (Legal)")
without extra variants. `cn_codes` FILLED 2026-07-04 from `suggest_lawyer_cn_codes` with
per-entry exclusions logged inline (Kay Mann MMANNING; Mark Taylor Notes UUIDs; James
Derrick shared-mailbox). Roster expansion (Jordan Mintz / Rex Rogers / broader) is a
data task deferred to Chat C — the suggest command makes each addition cheap.

"""

# Each entry: emails / display_variants / cn_codes are all matched (any hit = match).
# CN codes filled 2026-07-04 from suggest_lawyer_cn_codes output; case-insensitive matching
# means one canonical form per code suffices. Excluded candidates and why: see per-entry
# NOTEs below.
LAWYERS = [
    {
        "name": "Mark Haedicke",              # Managing Director & GC, Enron Wholesale
        "role": "in-house",
        "emails": ["mark.haedicke@enron.com"],            # VERIFY
        "display_variants": ["Haedicke, Mark", "Mark Haedicke"],
        "cn_codes": ["MHAEDIC", "496812c-a8259b42-8625650e-6a1dc1"],
    },
    {
        "name": "Sara Shackleton",
        "role": "in-house",
        "emails": ["sara.shackleton@enron.com"],           # VERIFY
        "display_variants": ["Shackleton, Sara", "Sara Shackleton"],
        "cn_codes": ["SSHACKL", "55ecbf6a-9860c778-86256498-74b7d9"],
    },
    {
        "name": "Elizabeth Sager",
        "role": "in-house",
        "emails": ["elizabeth.sager@enron.com"],           # VERIFY
        "display_variants": ["Sager, Elizabeth", "Elizabeth Sager"],
        "cn_codes": ["ESAGER", "50751f83-c6a72356-862564ea-583faa"],
    },
    {
        "name": "Richard Sanders",             # Assistant GC, litigation
        "role": "in-house",
        "emails": ["richard.sanders@enron.com"],           # VERIFY
        "display_variants": ["Sanders, Richard", "Richard Sanders"],
        "cn_codes": ["RSANDER", "fb40de6f-7345673d-86256575-5ae2f4"],
    },
    {
        "name": "Kay Mann",
        "role": "in-house",
        "emails": ["kay.mann@enron.com"],                  # VERIFY
        "display_variants": ["Mann, Kay", "Kay Mann"],
        "cn_codes": ["KMANN", "1389e042-45a8a4b3-862568aa-576fb7"],
        # NOTE: MMANNING (2 hits) EXCLUDED — likely a Manning-mailbox artifact; would
        # false-positive on real Manning (Marilyn etc.) emails.
    },
    {
        "name": "Mark Taylor",
        "role": "in-house",
        "emails": ["mark.taylor@enron.com"],               # VERIFY
        "display_variants": ["Taylor, Mark", "Mark Taylor"],
        "cn_codes": ["MTAYLO1"],
        # NOTE: two Notes UUIDs EXCLUDED — 947b69f4-... displays "Taylor, Mark A"
        # (different person from the lawyer "Taylor, Mark E (Legal)"), and cabbe9bb-...
        # displays only "Taylor, Mark" and cannot be safely disambiguated.
    },
    {
        "name": "Tana Jones",
        "role": "in-house",
        "emails": ["tana.jones@enron.com"],                # VERIFY
        "display_variants": ["Jones, Tana", "Tana Jones"],
        "cn_codes": ["TJONES", "16ec335a-26311472-86256498-74cdb3"],
    },
    {
        "name": "Gerald Nemec",
        "role": "in-house",
        "emails": ["gerald.nemec@enron.com"],              # VERIFY
        "display_variants": ["Nemec, Gerald", "Gerald Nemec"],
        "cn_codes": ["GNEMEC", "36908b2e-eb0947b-86256514-56e1e8"],
    },
    {
        "name": "James Derrick",               # EVP & General Counsel, Enron Corp
        "role": "in-house",
        "emails": ["james.derrick@enron.com"],             # VERIFY
        "display_variants": ["Derrick, James", "James Derrick"],
        "cn_codes": ["JDERRIC"],
        # NOTE: Mbx_annclegal (1 hit) EXCLUDED — the Mbx_ prefix is Exchange convention
        # for a shared/functional mailbox ("Legal - James Derrick Jr."). Adding it would
        # tag every mail to the legal-dept mailbox as being to Derrick personally.
    },
    {
        "name": "Marie Heard",
        "role": "in-house",
        "emails": ["marie.heard@enron.com"],               # VERIFY
        "display_variants": ["Heard, Marie", "Marie Heard"],
        "cn_codes": ["MHEARD"],
    },
]

# An email from any of these domains is an outside-counsel signal.
# velaw.com = Vinson & Elkins, Enron's principal outside counsel (well documented).
# Add other firms as they surface in the corpus — VERIFY before trusting.
EXTERNAL_COUNSEL_DOMAINS = [
    "velaw.com",
]

# ---------------------------------------------------------------------------
# GREP RECIPE — run once from the repo root to complete each lawyer.
#
# CN codes (the piece that can't be guessed). Find lines mentioning the surname,
# pull CN= fragments, drop the constant CN=RECIPIENTS:
#
#   grep -rhiE "haedicke" data/raw/ \
#     | grep -oiE "CN=[A-Za-z0-9-]+" | grep -viE "CN=RECIPIENTS" | sort -u
#
# Display-name variants actually present (catches middle initials, "E." forms, etc.):
#
#   grep -rhoiE "[A-Za-z]*,? *haedicke[^<>@]{0,20}" data/raw/ | sort -u | head
#
# Confirm the SMTP address if the person appears as clean SMTP at all:
#
#   grep -rhoiE "[a-z.]*haedicke[a-z.]*@[a-z.]+" data/raw/ | sort -u
#
# Repeat per surname. See DATA_REFERENCE.md for the authoritative address-form spec.
# ---------------------------------------------------------------------------