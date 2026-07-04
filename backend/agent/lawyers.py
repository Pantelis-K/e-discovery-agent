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
firstname.lastname@enron.com convention and MUST be verified. `display_variants` are
the predictable "Last, First" / "First Last" forms. `cn_codes` are EMPTY — they are
per-corpus identifiers that cannot be guessed. Fill them by running
`python manage.py suggest_lawyer_cn_codes` (mines them from the resolved participants;
prints candidates + hit counts for you to eyeball for collisions and paste in). The
raw grep recipe below still works as a manual fallback. ~2 hours (§5).

"""

# Each entry: emails / display_variants / cn_codes are all matched (any hit = match).
LAWYERS = [
    {
        "name": "Mark Haedicke",              # Managing Director & GC, Enron Wholesale
        "role": "in-house",
        "emails": ["mark.haedicke@enron.com"],            # VERIFY
        "display_variants": ["Haedicke, Mark", "Mark Haedicke"],
        "cn_codes": [],                                    # FILL from corpus
    },
    {
        "name": "Sara Shackleton",
        "role": "in-house",
        "emails": ["sara.shackleton@enron.com"],           # VERIFY
        "display_variants": ["Shackleton, Sara", "Sara Shackleton"],
        "cn_codes": [],
    },
    {
        "name": "Elizabeth Sager",
        "role": "in-house",
        "emails": ["elizabeth.sager@enron.com"],           # VERIFY
        "display_variants": ["Sager, Elizabeth", "Elizabeth Sager"],
        "cn_codes": [],
    },
    {
        "name": "Richard Sanders",             # Assistant GC, litigation
        "role": "in-house",
        "emails": ["richard.sanders@enron.com"],           # VERIFY
        "display_variants": ["Sanders, Richard", "Richard Sanders"],
        "cn_codes": [],
    },
    {
        "name": "Kay Mann",
        "role": "in-house",
        "emails": ["kay.mann@enron.com"],                  # VERIFY
        "display_variants": ["Mann, Kay", "Kay Mann"],
        "cn_codes": [],
    },
    {
        "name": "Mark Taylor",
        "role": "in-house",
        "emails": ["mark.taylor@enron.com"],               # VERIFY
        "display_variants": ["Taylor, Mark", "Mark Taylor"],
        "cn_codes": [],
    },
    {
        "name": "Tana Jones",
        "role": "in-house",
        "emails": ["tana.jones@enron.com"],                # VERIFY
        "display_variants": ["Jones, Tana", "Tana Jones"],
        "cn_codes": [],
    },
    {
        "name": "Gerald Nemec",
        "role": "in-house",
        "emails": ["gerald.nemec@enron.com"],              # VERIFY
        "display_variants": ["Nemec, Gerald", "Gerald Nemec"],
        "cn_codes": [],
    },
    {
        "name": "James Derrick",               # EVP & General Counsel, Enron Corp
        "role": "in-house",
        "emails": ["james.derrick@enron.com"],             # VERIFY
        "display_variants": ["Derrick, James", "James Derrick"],
        "cn_codes": [],
    },
    {
        "name": "Marie Heard",
        "role": "in-house",
        "emails": ["marie.heard@enron.com"],               # VERIFY
        "display_variants": ["Heard, Marie", "Marie Heard"],
        "cn_codes": [],
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