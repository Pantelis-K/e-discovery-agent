# Participant Address Format Survey

Read-only survey of `from_addr` / `to_addrs` / `cc_addrs` / `bcc_addrs` as
actually stored in the ingested SQLite DB. No writes, no schema changes, no
edits to `parsing.py` or `models.py` were made to produce this report —
investigation only.

## Source

- DB opened read-only: `sqlite3.connect("file:backend/db.sqlite3?mode=ro", uri=True)`.
  This is the only `*.sqlite3` under the repo that holds a `documents_document`
  table (the other two `*.sqlite3` hits are Chroma vector-store files under
  `data/chroma/` and `data/raw/chroma/`, unrelated to this survey).
- Table: `documents_document` (Django app `documents`, model `Document`).
- Participant list fields (`to_addrs`, `cc_addrs`) were parsed with the same
  tolerant logic as `agent/tools/read.py::_json_list` (`json.loads`, falling
  back to `[value]` for a bare unparsed string).
- To resolve how "one stored unit" is produced from a raw header, `documents/parsing.py`
  was read (not edited) — see `split_participants()`, `documents/parsing.py:131-149`.

## Coverage

| Metric | Value |
|---|---|
| Total rows in `documents_document` | **455,286** |
| Distinct `custodian` values | **151** |
| Corpus size | Matches the full EDRM base-email corpus (~455k) — **not** a dev subset |

Top custodians by row count: `kean-s` (19,846), `kaminski-v` (19,540),
`dasovich-j` (18,605), `beck-s` (14,109), `jones-t` (12,794), … (151 total).

**Raw on-disk representation of `to_addrs`** (one verbatim example, `typeof()` = `text`):

```
'["jsmith <jsmith@austintx.com>"]'
```

Confirmed: despite `models.py` declaring `to_addrs`/`cc_addrs` as `TextField`,
the column actually stores a **JSON-array-formatted string** (produced by
Django's SQLite backend serialising the Python list handed to it by
`parse_document_file()` in `parsing.py`), not a bare Python `list` repr and not
a plain '>,'-joined string. `_json_list`'s `json.loads` path is therefore the
normal case; its bare-string fallback is a safety net for any row where that
serialisation didn't happen.

`raw_headers` (JSON dict of the original `Key: value` header lines, e.g.
`{"Date": ..., "From": ..., "To": ..., "X-SDOC": ..., "X-ZLID": ...}`) is
populated for **455,286 / 455,286** rows (100%). This let the optional
spot-check below be done directly against the DB's own stored raw headers,
without needing to re-walk the original EDRM corpus files on disk.

## Category × field counts

Units classified per the task's category definitions. "Unit" = one already
split element of `from_addr` (1 unit if non-null) / `to_addrs` / `cc_addrs`.

| Category | from | to | cc | Total | % of all units |
|---|---:|---:|---:|---:|---:|
| smtp_internal | 1,091 | 48,327 | 26,765 | 76,183 | 3.406% |
| smtp_external | 9,022 | 140,636 | 22,399 | 172,057 | 7.691% |
| smtp_prefixed | 121,156 | 662,494 | 111,291 | 894,941 | 40.006% |
| x500_named | 85,263 | 218,452 | 19,073 | 322,788 | 14.429% |
| x500_blank | 0 | 1 | 0 | 1 | 0.000% |
| bare_name | 170,716 | 502,818 | 96,820 | 770,354 | 34.437% |
| other | 3 | 682 | 10 | 695 | 0.031% |
| **Field total (units)** | **387,251** | **1,573,410** | **276,358** | **2,237,019** | 100% |

**`smtp_prefixed` ("Display \<addr@domain\>") exists and is the single largest
category (40.0% of all units, 894,941 instances)** — e.g. every
`from_addr` populated with a display name has this shape whenever the sender
used SMTP addressing rather than Exchange X.500.

## Examples per category (up to 5, verbatim)

**smtp_internal**
- `mike.grigsby@enron.com`
- `MARK.WHITT@ENRON.COM`
- `Matt.Smith@enron.com`
- `jeff.richter@enron.com`
- `ywang@enron.com @ ENRON` — genuine single-unit oddity, see "Notable other cases" below

**smtp_external**
- `pallen70@hotmail.com`
- `moshuffle@hotmail.com`

**smtp_prefixed**
- `jsmith <jsmith@austintx.com>`
- `John J Lavorato <John J Lavorato/ENRON@enronXgate@ENRON>` — display name looks like an X.500 path but the bracket contents don't parse as `/O=.../CN=...`, so it falls through to this category (bracket contains `@` after `enronXgate`)
- `stanley.horton <stanley.horton@enron.com>`
- `dmccarty <dmccarty@enron.com>`
- `Keith Holst <Keith Holst/HOU/ECT@ect>`

**x500_named**
- `Allen, Phillip K. </O=ENRON/OU=NA/CN=RECIPIENTS/CN=PALLEN>`
- `Heizenrader, Timothy </O=ENRON/OU=NA/CN=RECIPIENTS/CN=Theizen>`
- `Gaskill, Chris </O=ENRON/OU=NA/CN=RECIPIENTS/CN=Cgaskill>`

**x500_blank** (only one instance in the whole corpus)
- `</o=ENRON/ou=NA/cn=Recipients/cn=Notesaddr/cn=5d91178a-cfe0ef46-8625694a-470259>`
  — doc `3.355838.INS1S2MM3A33CJUZSARGTBDHK2B5B4MLA`, `to_addrs`. Root cause
  confirmed below (not a genuinely blank display name).

**bare_name**
- `Phillip K Allen`
- `Ina Rangel`

**other**
- `<undisclosed-recipients:;>`
- `<AddressListTooLong-Suppressed:;>`
- `<Recipient List Suppressed:;>`
- `Undisclosed-Recipient <>`
- `Exchange System Administrator <.>`

## Splitter check — units containing more than one address

`split_participants()` (`documents/parsing.py:131-149`) works like this: if the
**whole field value** contains the literal substring `</O=` (uppercase),
it splits on the boundary `>\s*,\s*` (bracket-close + comma) anywhere in the
value; otherwise it splits on every plain comma. This has three confirmed
failure modes, found by diffing stored units against `raw_headers`:

### 1. Genuine merges: bare-comma addresses trailing an X.500 split (real bug)

Once a value contains any `</O=`, **every** `>,` in the value becomes a split
point — including `>,` after an ordinary bracketed SMTP address — but plain
comma-separated addresses **without** a bracket are never split apart, so they
stay merged into one stored unit.

- `[3.1162247.GHV4DD250XZIKHFHBZCQG3EV5Z0XSOIGA] to_addrs:` `"'smacfarland@gpch.org', 'lqcolombo@aol.com', 'Dad (E-mail)' <lwbthemarine@alltel.net>"` — raw To: header confirms this should be 3 separate recipients (`smacfarland@gpch.org`, `lqcolombo@aol.com`, `'Dad (E-mail)' <lwbthemarine@alltel.net>`); only the trailing bracket forced a split boundary.
- Same doc, second merged unit: `"'tommybomb88@hotmail.com', 'billy.brown2@compaq.com'"` (2 addresses, no bracket anywhere, never split).
- `[3.819694.IUJUPQGVQJSRDAQU5ZNOMWNJSMB1T4LVA] to_addrs:` `"'kevin.wellenius@frontiereconomics.com, gfergus@brobeck.com,' <seabron.adamson@frontiereconomics.com,>"` — raw To: confirms the source already presents this as a single quoted, comma-riddled display name in front of one bracket (`'Sanders, Richard B. </O=.../CN=Rsander>, 'kevin.wellenius@..., gfergus@...,' <seabron.adamson@...,>'`); the splitter correctly separated Sanders from this blob, but the blob itself contains 3 address-like tokens merged — this one is **source-corrupted data**, not a splitter defect (see item 3).

### 2. "Last, First" comma trap — hits BOTH splitter paths (quantified)

The parsing.py docstring says "Otherwise plain comma-split is safe" for values
without `</O=`, but display names in `Lastname, Firstname <addr>` form break
that assumption in both branches:

- **X.500 branch, case-sensitivity bug**: `X500_MARKER = "</O="` is matched
  case-sensitively, but **980 documents** have `to_addrs`/`cc_addrs` raw values
  using only a lowercase `</o=` DN marker (no uppercase `</O=` anywhere in the
  field). These values fall through to the plain-comma splitter instead of the
  `>,` splitter. Result: **2,313 "Lastname" + "Firstname \<DN\>" split pairs
  across 973 distinct documents** — e.g. `["Horton", "Stanley </o=ENRON/ou=NA/cn=Recipients/cn=Shorton>"]`,
  `["Piro", "Jim </o=ENRON/ou=NA/cn=Recipients/cn=Gwaddr/cn=HQ3.EM5.Jim Piro>"]`.
  This is the confirmed root cause of the sole `x500_blank` instance too: its
  raw To: value was `experience Enron, </o=ENRON/ou=NA/cn=Recipients/cn=Notesaddr/cn=...>`
  — lowercase-only marker → plain comma split → `"experience Enron"` peels
  off as a `bare_name` unit, leaving the DN with an **empty** prefix rather
  than one `x500_named` unit with prefix `"experience Enron"`.
- **Plain-comma branch (no X.500 marker at all)**: same trap, no case-sensitivity
  angle needed — e.g. the doc-3.346002 To: list (77 plain SMTP recipients, no
  `</O=` anywhere) contains `..., Sogomonian, Aram <Aram.Sogomonian@pacificorp.com>, ...`
  and `..., Kratka, Milan <MKratka@wolve.com>, ...`, each stored as two units:
  a lone-surname `bare_name` (`"Sogomonian"`, `"Kratka"`) plus a
  `smtp_prefixed` unit whose display is only the given name (`"Aram <...>"`,
  `"Milan <...>"`). Counted **1,352 such pairs across 609 distinct documents**.

Combined, these two variants of the same trap affect on the order of **~1,580
distinct documents** (973 + 609, some possible overlap not de-duplicated) and
account for essentially all of the `x500_blank` signal and a meaningful slice
of the `bare_name` / `smtp_prefixed` counts above — any surname-recovery logic
built on `x500_named`/`smtp_prefixed` prefixes should expect some fraction of
given-name-only or surname-only fragments from this cause.

### 3. False positives in a naive "looks like 2 addresses" heuristic

Checking each stored unit for "(has `@`) AND (has `CN=`)" over-flags
**single, correctly-split** participants whose bracket is an Exchange
IMCEAEX proxy address (which SMTP-encodes the DN inside the local part, so it
legitimately contains both `@` and `CN=`):

- `ISO Market Participants <IMCEAEX-_O=CAISO_OU=CORPORATE_CN=DISTRIBUTION+20LISTS_CN=ISO+20MARKET+20PARTICIPANTS@caiso.com>` — one mailing-list recipient, correctly split from a sibling `TSWG <TSWG@caiso.com>` recipient in the same raw To:.
- `/o=ENRON/ou=NA/cn=Recipients/cn=notesaddr/cn=a478079f-... <IMCEAEX-_O=ENRON_OU=NA_CN=RECIPIENTS_CN=Notesaddr_cn=a478079f-...@ENRON.com>` — one recipient whose "display name" is itself a raw (lowercase) X.500 path, paired with the IMCEAEX SMTP-encoded form of the *same* DN, not a second person.

Item 1 above (the genuine merges) remain confirmed splitter misses even after
excluding these false positives.

## x500_named: (CN code, display prefix) pairs — 10 examples

| CN code | Display prefix | doc_id | field |
|---|---|---|---|
| PALLEN | Allen, Phillip K. | 3.819233.ISFC2QQ2RQGQPDPBVZKXXUZG1ZVTYC4ZA | from_addr |
| Theizen | Heizenrader, Timothy | 3.819233.ISFC2QQ2RQGQPDPBVZKXXUZG1ZVTYC4ZA | to_addrs |
| Cgaskill | Gaskill, Chris | 3.819234.CSUJUIGZLLRJZUBQDZGF1UIGSZRKMLXHB | to_addrs |
| Ssever | Sever, Stephanie | 3.819235.HSAWNJFRS3AIN5YQKU0F0E4E4QL03TAIB | to_addrs |
| Kbuckley | Buckley, Karen | 3.819236.IHYCQVDGJY3JUG4K4KKX5UAFGFMMSELAB | to_addrs |
| Jgosset | Gossett, Jeffrey C. | 3.819237.AO10KSBZOZVAPJQHT3ON4E2LNTIY3KTYA | to_addrs |
| Jwebb | Webb, Jay | 3.819238.DGV5KV3SUAHHHLD30EKN22RBKK1MF0M2A | to_addrs |
| Jtholt | Tholt, Jane M. | 3.819239.B0QAZTPGWGYYGJNDAOX2I3FWH20EZGORA | to_addrs |
| Mgrigsb | Grigsby, Mike | 3.819239.B0QAZTPGWGYYGJNDAOX2I3FWH20EZGORA | to_addrs |
| Jslone | Slone, Jeanie | 3.819247.LT2DBZWJE303V2FRPJ3WFVKUNP5R22JIA | to_addrs |

CN code and full `"Lastname, Firstname"` prefix pair cleanly for these
examples. As noted above, ~973 documents have this pairing degraded to a
given-name-only prefix due to the lowercase-marker splitter bug.

## Bcc

**Confirmed empty for the entire corpus**: `bcc_addrs` is non-null/non-empty
in **0 / 455,286** rows. This matches `parsing.py:246` — `bcc_addrs` is
hard-coded to `None` at ingestion ("never populated (Bcc absent from
corpus)") — there is no exception to find because `bcc_addrs` is never set
from parsed data in the first place.

## Notable "other" cases (33 distinct patterns found, 695 units total)

- **RFC 2822 group-list / suppression syntax** (bracket contains a bare label
  + `:;`, no DN, no email): `<undisclosed-recipients:;>`,
  `<AddressListTooLong-Suppressed:;>`, `<Recipient List Suppressed:;>`,
  `<recipient list not shown: ;>`, `<unspecified-recipients:;>`,
  `<The Risk Desk:;>`, `<Comp Subscriber--The Desk:;>`, `<EMF 20 Participants:;>`,
  `<emf20:;>`, `<affiliates:;>`, `<sponsors:;>`, `<ER:;>`, `<The Desk Subscriber:;>`.
- **Role/list display names with an empty or junk bracket**:
  `Undisclosed-Recipient <>`, `John H Herbert <>`, `Power - Eastern <>`,
  `Exchange System Administrator <.>`.
- **Genuinely truncated/corrupted addresses already in the raw corpus**
  (confirmed via `raw_headers` — not a splitter artifact): e.g. raw Cc header
  `"'hcameron@uclink.berkeley.edu'" <hcameron, "'jeff.dasovich@, "'lfried@uclink.berkeley.edu'"<lfried>`
  (doc `3.52566...`) is already three broken, mid-address-truncated fragments
  in the source header before any splitting; comma-splitting them individually
  is therefore correct behaviour on corrupt input, producing stored units
  like `"'jeff.dasovich@` and `"'lfried@uclink.berkeley.edu'"<lfried>`.
- **`Michael Enbar <[No.email.address.found>` / `Dick Kazarian <[No.email.address.found>`**
  — literal placeholder text substituted for a missing address in the original
  export, preserved verbatim.
- **Percent/URL-style encoded proxy address**: `MCEANOTES-+22Joseph+20G+2EGalea+22+20+3Cgalea+40mcgown+2Ecom+3E+40ENRON@ENRON.com <I>` — bracket contains a lone `<I>` fragment split off from a longer address, source-truncated.
