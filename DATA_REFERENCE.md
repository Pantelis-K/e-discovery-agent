# Data Reference: Extracted Enron EDRM v2 Text Corpus

Structural documentation of the on-disk corpus at `data/raw/`. Every claim
below was verified by direct inspection of the actual files (via shell/awk
commands — `find`, `grep`, `file`, `stat`, `xxd`) rather than assumed from
the source tar's naming conventions. Scope is corpus structure only — labels,
qrels, and the evaluation/seed-set side are **not** covered here.

This document reflects the state of `data/raw/` as inspected; it does not
cover how the data got there or whether it should be re-extracted.

## 1. Directory layout

```
data/raw/
├── edrm-enron-v2_<custodian>_xml.zip/        ← directory, NOT an archive
│   └── text_NNN/                              ← one or more per custodian
│       ├── 3.<num>.<HASH>.txt                 ← base email
│       ├── 3.<num>.<HASH>.1.txt                ← attachment part 1
│       └── ...
├── docids-v2.csv.bz2
├── msg-uniqmsg.csv.bz2
├── seed.csv
├── uniqmsg.csv.bz2
└── edrmv2txt-v2.tar.bz2                        ← original source archive
```

**The `.zip`-named entries are plain directories, not zip archives.**
Confirmed via `stat`:

```
$ stat data/raw/edrm-enron-v2_allen-p_xml.zip
  File: data/raw/edrm-enron-v2_allen-p_xml.zip
  Size: 0          Blocks: 0          IO Block: 65536  directory
```

This naming is inherited directly from the original tar's internal paths —
the bz2 bundle itself stores entries as `edrm-enron-v2_<custodian>_xml.zip/text_NNN/<file>.txt`,
i.e. the `.zip` suffix is a naming artifact from whatever upstream process
built `edrmv2txt-v2.tar.bz2`, not a sign of nested archives. Every document
inside is a `.txt` file, never `.xml` despite the `_xml` in the folder name.

### Custodian and file counts

- **159 custodian directories** total.
- **685,592 `.txt` files** total. Confirmed three independent ways:
  - `find data/raw -iname "*.zip" -type d -exec find {} -type f \;` → 685,592
  - PowerShell `Get-ChildItem -Recurse -File | Measure-Object` → 685,592 files, 3,991,162,863 bytes (≈3.72 GB)
  - `tar -tjf edrmv2txt-v2.tar.bz2 | wc -l` on the original source archive → 685,592 (exact match, confirming the on-disk extraction is complete and matches the source archive 1:1)
- 685,592 also matches the published unique-message count for the TREC 2010
  EDRM v2 de-duplicated text bundle, which is corroborating (not
  independently re-verified against an external source in this session).

**Discrepancy resolved:** an earlier count of 624,869 files came from a glob
(`*_xml.zip`) that only matches directory names ending literally in
`_xml.zip`. It silently missed 10 directories that use a different naming
pattern for Enron's two largest custodians, which were split into parts:

```
edrm-enron-v2_kaminski-v_xml_1of2.zip   25,049 files
edrm-enron-v2_kaminski-v_xml_2of2.zip    9,244 files
edrm-enron-v2_kean-s_xml_1of8.zip        8,431 files
edrm-enron-v2_kean-s_xml_2of8.zip        2,358 files
edrm-enron-v2_kean-s_xml_3of8.zip        3,487 files
edrm-enron-v2_kean-s_xml_4of8.zip          763 files
edrm-enron-v2_kean-s_xml_5of8.zip          940 files
edrm-enron-v2_kean-s_xml_6of8.zip          808 files
edrm-enron-v2_kean-s_xml_7of8.zip        9,481 files
edrm-enron-v2_kean-s_xml_8of8.zip          162 files
                                  total:  60,723 files
```

`624,869 + 60,723 = 685,592` — exact match. The corpus was fully extracted
all along; the earlier count just used an incomplete glob pattern. **Any
future tooling that enumerates custodian directories must match `*.zip`
(directories), not `*_xml.zip`**, or it will silently skip these two
custodians.

### `text_NNN` subfolders

Each custodian directory contains one or more `text_NNN` subfolders
(`text_000`, `text_001`, ...):

- 151 of 159 top-level directories have exactly one subfolder (`text_000`
  only).
- The remaining 8 have multiple: counts observed were `text_001` (29
  occurrences across the corpus), `text_002` (13), `text_003` (10),
  `text_004`/`text_005` (3 each), `text_006`/`text_007` (2 each), up to a
  max of 8 subfolders in one directory (`edrm-enron-v2_dasovich-j_xml.zip`).
- File counts per subfolder vary a lot and don't follow an obvious fixed
  batch size — e.g. `edrm-enron-v2_beck-s_xml.zip` has `text_000`=7,252,
  `text_001`=4,085, `text_002`=3,467, `text_003`=1,255. **The rule governing
  how files get split across `text_NNN` subfolders was not determined** —
  see Open Questions.
- No non-`.txt` files (no manifest, index, or metadata sidecar file) were
  found anywhere under any inspected custodian directory. All metadata lives
  inside the `.txt` files themselves.

## 2. Filename / doc-id format

Pattern: `3.<NNNNNN>.<HASH>[.<N>].txt`

Example: `3.818908.A0CV1HWH4CFTZMBCQWRRDZRJFIKDBFYJB.1.txt`

- **`3.`** — a constant prefix observed on every single file inspected
  across all sampled custodians. Its meaning was not determined from the
  corpus alone (see Open Questions).
- **`NNNNNN`** — a variable-length numeric segment (e.g. `818908`). Appears
  unique per base message. Exact derivation (sequential export counter vs.
  something else) not verified.
- **`HASH`** — a ~26–36 character uppercase alphanumeric token, unique per
  document. Looks hash-derived; the exact algorithm/source was not
  determined.
- **Trailing `.N`** — attachment part number. No suffix = base email.

This matches the doc-id convention already confirmed against `seed.csv` /
`docids-v2.csv.bz2` in a prior session (doc id = filename minus `.txt`).

**Verified: base vs. attachment relationship.** Checked across 5 custodians
(allen-p, beck-s, dasovich-j, lay-k, skilling-j; up to 4,438 suffixed doc-ids
checked in dasovich-j alone) — **every suffixed file has a matching base
file, zero orphans found**.

**Verified: a `.N` suffixed file is genuinely attachment content**, not
another email. Example (`edrm-enron-v2_allen-p_xml.zip/text_000/`):

- Base `3.818908.A0CV1HWH4CFTZMBCQWRRDZRJFIKDBFYJB.txt` — a short email
  whose trailing line reads `Attachment: stage_pivot8_9.xls type=application/msexcell`
  (see Example 3 below, shown in full).
- `3.818908.A0CV1HWH4CFTZMBCQWRRDZRJFIKDBFYJB.1.txt` — 27,014 bytes of
  tab-separated numeric data (a flattened spreadsheet dump), consistent with
  extracted `.xls` content, not an email.

## 3. Inside a text file — anatomy

```
[header block: "Key: value" lines, no fixed field set — see §4]
[blank line]
[body: free text]
[blank line(s)]
***********
EDRM Enron Email Data Set has been produced in EML, PST and NSF format by ZL Technologies, Inc. This Data Set is licensed under a Creative Commons Attribution 3.0 United States License <http://creativecommons.org/licenses/by/3.0/us/> . To provide attribution, please cite to "ZL Technologies, Inc. (http://www.zlti.com)."
***********
[optional: Attachment: <filename> type=<mimetype>]
```

**Boilerplate footer:** present in **900/900** sampled base-email files
(100%, sample spans 15 custodians). **Absent from attachment-suffixed
(`.N.txt`) files** — checked 3 attachment files directly, footer present in
0/3. The footer is emitted once per base-email record only.

**`Attachment:` line:** appears after the boilerplate, only when the
message had an attachment. Full-corpus scan (all 685,592 files):
**241,825 `Attachment:` lines found**, of which **241,635 (99.92%) match the
exact pattern** `Attachment: <name> type=<mimetype>`. The 190 non-conforming
lines are almost all free-text variants with no `type=` field (e.g.
`Attachment: Data requested by the EOB:`), plus a couple of files flagged by
`grep` as binary rather than text (see §Encoding).

### Example 1 — internal-to-internal (X.500 addressing), full file

`data/raw/edrm-enron-v2_allen-p_xml.zip/text_000/3.819233.ISFC2QQ2RQGQPDPBVZKXXUZG1ZVTYC4ZA.txt`

```
Date: Wed, 6 Jun 2001 15:16:36 -0700 (PDT)
From: Allen, Phillip K. </O=ENRON/OU=NA/CN=RECIPIENTS/CN=PALLEN>
To: Heizenrader, Timothy </O=ENRON/OU=NA/CN=RECIPIENTS/CN=Theizen>
X-SDOC: 1151881
X-ZLID: zl-edrm-enron-v2-allen-p-5308.eml

Tim,

I know you looked into this before but we are still having issues with Mike Grigsby's access to the west power site.  He can view some parts of the website but cannot view the heatrate information under the testing tab.  Does he have some sort of reduced access?  Our IT (Collin)  looked at Mike's access but claimed that it must be on the Portland end.  Sorry to bother you with this again, but can you help?

Phillip

***********
EDRM Enron Email Data Set has been produced in EML, PST and NSF format by ZL Technologies, Inc. This Data Set is licensed under a Creative Commons Attribution 3.0 United States License <http://creativecommons.org/licenses/by/3.0/us/> . To provide attribution, please cite to "ZL Technologies, Inc. (http://www.zlti.com)."
***********
```

### Example 2 — external recipient with Cc, full file

`data/raw/edrm-enron-v2_allen-p_xml.zip/text_000/3.819187.GTNMNBYMMZJLEVQURSKRI2HBYUEPZX5GA.txt`

```
Date: Mon, 5 Mar 2001 07:21:00 -0800 (PST)
From: Phillip K Allen
To: cbpres@austin.rr.com
Cc: llewter@austin.rr.com, jacquestc@aol.com
X-SDOC: 951080
X-ZLID: zl-edrm-enron-v2-allen-p-3812.eml

George,

I am back in the office and ready to focus on the project.  I still have the 
concerns that I had last week.  Specifically that the costs of our project 
are too high.  I have gathered more information that support my concerns.  
Based on my research, I believe the project should cost around $10.5 
million.  The components are as follows:

 Unit Cost, Site work, &
 builders profit($52/sf)   $7.6 million

 Land      1.15

 Interim Financing     .85

 Common Areas       .80

 Total     $10.4

Since Reagan's last 12 units are selling for around $190,000, I am unable to 
get comfortable building a larger project at over $95,000/unit in costs.  

Also, the comps used in the appraisal from Austin appear to be class A 
properties.  It seems unlikely that student housing in San Marcos can produce 
the same rent or sales price.  There should adjustments for location and the 
seasonal nature of student rental property.  I recognize that Sagewood is 
currently performing at occupancy and $/foot rental rates that are closer to 
the appraisal and your pro formas, however, we do not believe that the market 
will sustain these levels on a permanent basis.  Supply will inevitablely 
increase to drive this market more in balance.

After the real estate expert from Houston reviewed the proforma and cost 
estimates, his comments were that the appraisal is overly optimistic.  He 
feels that the permanent financing would potentially be around $9.8 million.  
We would not even be able to cover the interim financing.

Keith and I have reviewed the project thoroughly and are in agreement that we 
cannot proceed with total cost estimates significantly above $10.5 million.   
We would like to have a conference call tomorrow to discuss alternatives.

Phillip 

  


***********
EDRM Enron Email Data Set has been produced in EML, PST and NSF format by ZL Technologies, Inc. This Data Set is licensed under a Creative Commons Attribution 3.0 United States License <http://creativecommons.org/licenses/by/3.0/us/> . To provide attribution, please cite to "ZL Technologies, Inc. (http://www.zlti.com)."
***********
```

### Example 3 — base email with an attachment line, full file

`data/raw/edrm-enron-v2_allen-p_xml.zip/text_000/3.818908.A0CV1HWH4CFTZMBCQWRRDZRJFIKDBFYJB.txt`

```
Date: Mon, 11 Sep 2000 09:19:00 -0700 (PDT)
From: Phillip K Allen
To: pallen70@hotmail.com
X-SDOC: 948921
X-ZLID: zl-edrm-enron-v2-allen-p-1738.eml



***********
EDRM Enron Email Data Set has been produced in EML, PST and NSF format by ZL Technologies, Inc. This Data Set is licensed under a Creative Commons Attribution 3.0 United States License <http://creativecommons.org/licenses/by/3.0/us/> . To provide attribution, please cite to "ZL Technologies, Inc. (http://www.zlti.com)."
***********
Attachment: stage_pivot8_9.xls type=application/msexcell
```

(Its attachment part, `...A0CV1HWH4CFTZMBCQWRRDZRJFIKDBFYJB.1.txt`, is a
27,014-byte tab-separated numeric dump — the extracted spreadsheet content —
not reproduced here as it is not meaningful in prose form.)

## 4. Header fields — verified

Sampled 900 base-email files (60 files each from 15 custodians spread across
the corpus: allen-p, bailey-s, dasovich-j, haedicke-m, kean-s_1of8, lay-k,
mann-k, rapp-b, shackleton-s, skilling-j, taylor-m, watson-k, whalley-g,
ybarbo-p, zufferli-j). Header block = everything up to the first blank line.

| Field | Present | % |
|---|---|---|
| `Date:` | 900 / 900 | 100% |
| `X-SDOC:` | 900 / 900 | 100% |
| `X-ZLID:` | 900 / 900 | 100% |
| `Subject:` | 868 / 900 | 96.4% |
| `From:` | 751 / 900 | 83.4% |
| `To:` | 592 / 900 | 65.8% |
| `Cc:` | 102 / 900 | 11.3% |
| `Bcc:` | 0 / 900 | 0% (never observed) |
| `Message-ID:` / `In-Reply-To:` / `References:` | 0 / 900 | 0% (never observed as a real header — see §6) |

**`From:`/`To:` completeness varies enormously by custodian** — this is not
a uniform corpus-wide rate. Per-custodian counts (of 60 sampled each):

| Custodian | From | To | Subject |
|---|---|---|---|
| allen-p | 60/60 | 60/60 | 40/60 |
| bailey-s | 25/60 | **1/60** | 58/60 |
| dasovich-j | 60/60 | 60/60 | 56/60 |
| haedicke-m | 34/60 | 17/60 | 60/60 |
| kean-s_1of8 | 59/60 | 37/60 | 60/60 |
| lay-k | 24/60 | 9/60 | 60/60 |
| mann-k | 60/60 | 60/60 | 59/60 |
| rapp-b | 60/60 | 60/60 | 59/60 |
| shackleton-s | 60/60 | 59/60 | 60/60 |
| skilling-j | **12/60** | **12/60** | 59/60 |

(Scan of the remaining 5 sampled custodians was interrupted by a shell
timeout and not completed — see Open Questions.)

**Practical implication:** a downstream parser cannot assume `From:`/`To:`
exist. Some custodians (bailey-s, lay-k, skilling-j) have this missing on a
majority of messages — likely personal notes, calendar items, or drafts
where those fields were never populated in the original PST/NSF/EML source.

**Example of missing `To:`** (`bailey-s`):
```
Date: Wed, 19 Jul 2000 21:00:00 -0700 (PDT)
From: Susan Bailey
X-SDOC: 421755
X-ZLID: zl-edrm-enron-v2-bailey-s-1000.eml
```

**Example of missing `From:`** (`bailey-s`):
```
Date: Wed, 19 Jul 2000 17:00:00 -0700 (PDT)
Subject: Out Of Office
X-SDOC: 421761
X-ZLID: zl-edrm-enron-v2-bailey-s-1005.eml
```

**Full set of header keys observed** across the sample: `Date`, `From`,
`To`, `Cc`, `Subject`, `X-SDOC`, `X-ZLID`. No other header keys were found.
`X-SDOC` and `X-ZLID` look like ZL Technologies' own export/document
identifiers (not standard email headers) — present on literally every
file, making them the only two fields reliable enough to key on
unconditionally.

## 5. Address formats — verified

Three forms coexist, sometimes within the same custodian's outbound mail:

1. **Clean address**: `name@enron.com` or an external domain
   (`cbpres@austin.rr.com`).
2. **Exchange/Notes X.500 distinguished name**:
   `Allen, Phillip K. </O=ENRON/OU=NA/CN=RECIPIENTS/CN=PALLEN>`
3. **Bare display name, no address at all**: `From: Phillip K Allen`

This was originally observed in `allen-p` alone and has now been verified
corpus-wide: a full-corpus scan found **138,393 X.500-style address lines**
(`From:`/`To:`/`Cc:` combined) across all custodians, not a one-off pattern.

**Blank display names do occur**: 1,029 of the 138,393 X.500 lines (0.74%)
have no display name text before the `<...>` bracket, e.g.
`From:  </O=ENRON/OU=NA/CN=RECIPIENTS/CN=RZIVIC>`.

### The CN= mapping question — precise answer

**Does `CN=<code>` reliably correspond to one person?** Yes, when tested
against single-recipient header lines. A random sample of 20 distinct CN
codes drawn from across the corpus (not just allen-p) each mapped to
exactly one display name wherever data was available, e.g.:

- `CN=Jtholt` → always `Tholt, Jane M.` (verified across multiple
  custodians' mail, not just messages sent by Jane Tholt herself)
- `CN=PALLEN` → always `Allen, Phillip K.`
- `CN=AARONOW` → `Aronowitz, Alan` (2 distinct names on an *unfiltered*
  first pass — this turned out to be a false positive from a parsing bug
  described below, corrected by restricting to single-recipient lines)

**Important caveat on multi-recipient lines**: when a `To:`/`Cc:` line lists
more than one recipient (comma-separated `Name </X.500>` entries), naive
comma-based parsing is genuinely ambiguous, because the display-name format
itself (`Last, First M.`) also uses commas. Example:
`To: Tholt, Jane M. </O=.../CN=Jtholt>, Grigsby, Mike </O=.../CN=Mgrigsb>` —
splitting on `,` blindly will misattribute names to the wrong CN code. A
correct parser needs to treat each `Name </X.500-string>` unit as a whole
(e.g. split on the `>,` boundary, not on every comma). This was confirmed by
first getting inconsistent-looking CN-to-name mappings, then re-running the
check restricted to lines with exactly one `<...>` bracket, which resolved
to a clean 1-to-1 mapping.

**No mapping/directory file exists anywhere in the corpus.** No manifest,
address book, or alias table was found under any custodian directory (see
§1). A CN → display-name mapping is **derivable**, but only by scanning all
header lines across the whole corpus and pairing each co-occurring
`(CN=code, display name)` fragment — there is no shortcut, and it must
handle the multi-recipient parsing caveat above correctly.

**Critically: even a fully derived mapping only yields a human display
name** (e.g. `"Tholt, Jane M."`), **never a canonical email address**. No
`@enron.com` address is given anywhere in the corpus for an X.500-addressed
person. Reconstructing an actual address (e.g. guessing
`jane.tholt@enron.com`) would require external information not present in
this corpus and was not attempted or verified here.

## 6. Threading — verified, and it's a real gap

**No `Message-ID`, `In-Reply-To`, `References`, or any `Thread-*` header was
ever found in the header-block position** of any sampled file (0/900 in the
structured sample, confirmed separately for allen-p).

The only occurrence of the string `Message-ID:` found anywhere was embedded
**inside a quoted bounce/non-delivery-report body**, not a real header of
the containing message:

```
Message-ID: <OF1845F8DC.31DE1EAF-ON86256A1E.00535FA2@enron.com>
```
(found inside the quoted SMTP transcript of a "Nondeliverable mail" message,
several lines into the body — not part of the top message's own header
block.)

**There is no structured field usable for reconstructing reply/forward
chains.** The only available proxies, none of them reliable:
- The doc-id family (base + `.N` attachments) groups a message with its own
  attachments — this is not threading, just one message's parts.
- `Subject:` text (informal `RE:`/`FW:` prefixes appear in some bodies/quoted
  content, not systematically in the `Subject:` field itself in the samples
  reviewed) — a heuristic at best, not verified as reliable.
- Quoted/forwarded body text (see §7) — would require free-text parsing.

## 7. Body content — verified

**Quoted/forwarded content is common but not universal.** In the 900-file
sample: `"Forwarded by"` pattern found in 140/900 files (15.6%),
`"Original Message"` pattern found in 97/900 files (10.8%) (some overlap
likely, not deduplicated against each other).

**Not every record is a strict email.** Some files contain pasted
calendar/meeting-invite text instead of email prose, with no `Subject:` or
`To:` header at all, e.g. (`allen-p`):
```
Date: Mon, 25 Sep 2000 07:01:00 -0700 (PDT)
From: Phillip K Allen
To: Ina Rangel
X-SDOC: 948903
X-ZLID: zl-edrm-enron-v2-allen-p-1720.eml

---------------------- Forwarded by Phillip K Allen/HOU/ECT on 09/25/2000 
02:01 PM ---------------------------


	Reschedule
Chairperson: Richard Burchfield
Sent by: Cindy Cicchetti

Start: 09/28/2000 01:00 PM
...
```

**Attachment reference format**: `Attachment: <filename> type=<mimetype>`,
appears after the boilerplate footer, only in base-email files. Verified
consistent at 99.92% across the full corpus (see §3).

## 8. Encoding — verified

Sampled `file(1)` output on 900 files:

| Classification | Count | % |
|---|---|---|
| ASCII text, CRLF line terminators | 853 | 94.8% |
| UTF-8 text, CRLF line terminators | 31 | 3.4% |
| `data` (unrecognized / binary) | ~15 | ~1.7% |

Line endings are **CRLF** (`\r\n`), confirmed via hex dump of a header block
(`0d 0a` after each header line).

A further sample of 300 files found **0 files containing any byte ≥ 0x80**
— no raw Latin-1/Windows-1252 high-byte content observed in that subsample.
This is a sample, not exhaustive — cannot rule out such content existing
elsewhere in the 685,592-file corpus.

**The `data`-classified files are a real, if rare, corruption case**, not a
detection false-positive. Manually inspected example:
`edrm-enron-v2_allen-p_xml.zip/text_000/3.818994.DT1SUE0DAA2UKNGRVJH3O41MKYFMIHAWB.txt`
(a **base** email file, no `.N` suffix, 16,228 bytes):

- Opens with a normal plain-text header block (`Date`/`From`/`To`/`Subject`/
  `X-SDOC`/`X-ZLID`) and includes the ZL boilerplate text.
- But 10,281 of its 16,228 bytes are NUL (`0x00`) bytes, forming what a hex
  dump shows to be a raw OLE2/MS-Office compound-file fragment (readable
  UTF-16-ish stream names `SummaryInformation` / `DocumentSummaryInformation`
  are visible in the hex dump).
- In other words: for a small fraction of records, raw binary attachment
  bytes leaked directly into what is nominally a plain-text base-email file,
  not just into the `.N` attachment part. A downstream pipeline needs to
  handle this defensively (e.g. detect and skip/quarantine non-text `.txt`
  files) rather than assume every `.txt` file is parseable as text.
- Extrapolating from the 900-file sample (~1.7% affected), the full
  685,592-file corpus may contain on the order of 1,000+ such files — this
  is an extrapolation from a small sample, not a full-corpus count (see
  Open Questions).

## Open questions / unverified

Flagged explicitly rather than guessed at:

- **Meaning of the leading `3.` prefix** in every doc id — observed as a
  corpus-wide constant, but its origin/meaning (TREC batch id? source-system
  code?) was not determined from the corpus alone.
- **Meaning/derivation of the numeric segment and the HASH segment** in doc
  ids — not verified; likely a sequential export id and a content- or
  path-derived hash respectively, but the exact algorithm was not confirmed.
- **Header-field prevalence percentages (§4) are sampled, not exhaustive** —
  900 files across 15 of 159 custodians (with the per-custodian breakdown
  covering only 10 of those 15 custodians before a shell timeout cut the
  scan short). Actual rates could differ in the 144+ unsampled custodians.
- **Non-ASCII/encoding prevalence (§8) is sampled, not exhaustive** — 300
  files checked for high-bit bytes, 900 files checked via `file(1)`. The
  ~1.7% "data"/binary rate and the "0 files with non-ASCII bytes" finding
  are both extrapolations from small samples, not full-corpus counts.
- **Rule governing `text_NNN` subfolder splits** — no evidence of a fixed
  file-count threshold; not determined what actually drives the split.
- **Full-corpus count of `data`/binary-corrupted `.txt` files** was not
  computed; only estimated by extrapolation from the 900-file sample (§8).
- **Text-extraction methodology** (how the original PST/NSF/EML sources were
  converted to these `.txt` files by ZL Technologies/TREC organizers) is not
  documented anywhere inside the corpus itself; inferred only indirectly
  from artifacts like the OLE2 leakage case in §8.
- **Whether a custodian's own CN code is always guessable from their folder
  name** (e.g. `allen-p` → `CN=PALLEN`) — observed to hold in the one case
  checked, not verified as a corpus-wide rule across all 159 custodians.
- **No attempt was made** to derive or validate real `@enron.com` addresses
  for X.500-addressed individuals; only the display-name mapping was
  verified (§5). Any address-guessing scheme is unverified and out of scope
  for this document.
