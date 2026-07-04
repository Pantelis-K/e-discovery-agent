# Decision Log

Entries follow the format (ordered most recent to least):
**Date | Decision title**
- Context:
- Options considered:
- Decision:
- Rationale:
- Revisit if:

## 2026-07-04 — Participant identity resolution: structured display units, splitter fix, structural privilege matching, scoped-retrieval tool

**Context.** The revision-4 corpus-wide participant-format survey
(`docs/participant-format-survey.md`) quantified that participants appear in three
inconsistent forms (SMTP / X.500 DN / bare display name) with meaningful mis-splits in
the previous `documents/parsing.py::split_participants` — case-sensitive `</O=` marker
missing lowercase `</o=` (980 docs), `Last, First <addr>` comma trap under the plain-comma
branch (609 docs), and bare-comma addresses merged into a single unit beside an X.500
recipient. Downstream: `check_privilege_signals` did substring matching over raw
participant text (surname-collision-prone, mis-split-blind), and the reviewer UI would
have to render raw X.500 DNs and IMCEAEX proxy strings without any canonical display.
The 2026-07-03 Pending item **General alias → canonical-identity resolution** flagged
this as a Mode-1 decision to make before privilege matching could be trusted, and coupled
to it, the lawyer-list-scope Pending item on how to fill CN codes.

This entry records the resolutions of those Pending items, plus three closely-coupled
decisions that fall out of the same work (splitter fix, structural matching, and the new
scoped-retrieval tool that supersedes the cut `extract_entities`). All four decisions are
implemented in code and verified against the full 455,286-row live DB.

---

**Decision 1 — Participant identity resolution: structured display units on `Document`, deterministic at ingest, no separate registry table. Bracket-anchored splitter with a From:-only special case.**

Options considered:
1. **Bounded/lazy resolver at read time** — resolve only participants that appear in reviewed documents, per read_document call. Cheaper to build; leaves everything not-read unresolved; couples resolution to the loop path; harder to render consistently across queue / active document / audit panels.
2. **Precomputed corpus-wide registry table** — the previously-cut option; identity table keyed by CN code + display + email; ingestion populates. Reintroduces the cut work; needs identity clustering with no ground truth to score against.
3. **Structured units on `Document`, resolved deterministically at ingest, no registry** (SELECTED) — each row carries `from_display` (one JSON unit or null) and `to_display`/`cc_display` (JSON arrays), where each unit is `{raw, display, kind, cn_code, email, domain}`. No canonical person ID: two units with the same `cn_code` are the same person by construction; two units with the same `display` are almost certainly the same person; two SMTP-vs-X.500 forms of the same person stay unlinked and the reviewer adjudicates. Raw From/To/Cc kept alongside for audit.

Decision: Option 3. Structured units on `Document`. Backfill from `raw_headers` (populated 100%). Chroma intentionally untouched — bodies are unchanged so no re-embed needed; Chroma's `sender` metadata is a display hint only, not authoritative for participant matching.

**Splitter — bracket-anchored, `resolve_field` for multi-participant fields and `resolve_unit` for the single-participant From:**. `resolve_field` walks the raw value, anchors on `<...>` (which never contains a real separator in this corpus), peels complete email tokens off the front of each pre-bracket prefix, and treats the trailing non-email run as that bracket's display name. This fixes all three survey defects at once (case-insensitive brackets, `Last, First <addr>` preserved, bare-comma addresses split correctly). It has a deliberate over-grouping bias: a bracketless `"Last, First"` over-splits into `"Last"` + `"First"` bare-name units. `From:` always carries one participant, so ingest / backfill calls `resolve_unit` directly, which does NOT comma-split — this preserves bare `"Last, First"` sender names as one bare_name unit. The initial backfill used `resolve_field` for From and lost the given name on 6,165 `from_display` rows (verified — `Stark, Cindy` → `Stark`, `Kaminski, Vince J` → `Kaminski`, etc.); corrected same day and re-run idempotently repaired all 6,165.

**Keep-both raw + display.** Raw `from_addr` / `to_addrs` / `cc_addrs` are retained on the row. Two reasons: minimal disruption to any code reading raw participants (search, audit trail regeneration, future re-parsing), and audit-verbatim guarantee — the resolver's per-unit `raw` field is canonicalised (whitespace normalised, trailing separator dropped), not byte-for-byte from the header, so pristine text lives on `raw_headers` + the raw `_addrs` columns.

**CN → display-name registry stays cut (reinforced).** The 2026-07-03 Pending item asked whether to revive it. The survey's finding — exactly ONE `x500_blank` unit in the whole 2.2M-unit corpus, and even that one was a splitter artifact from a lowercase `</o=` value now correctly parsed — collapses the argument for a registry. Every X.500 DN in the corpus carries its display prefix inline; there is no case where a lookup table would recover a name that isn't already sitting next to the DN.

**`extract_entities` stays cut.** The "find people" need surfaced by the corrections work is served by Decision 4 (structured lookup), not by LLM entity extraction over free body text.

Rationale: puts identity where it belongs (on the participant unit, deterministic, at ingest) without paying for a canonical person ID the corpus can't support. The reviewer UI can render a uniform canonical name for every participant; the agent can apply corrections that name individuals to future documents through structural matching; the audit trail records which key hit ("via cn_code=Sshackl" vs "via display 'Shackleton, Sara M.'").

Spec edits (applied): §3 read_document (Document shape includes `*_display`); §5 Address formats (corrected splitter, three fixed defects with counts, over-grouping bias, From:-only `resolve_unit` special case, keep-both, registry-cut reinforcement); §6 `documents` schema (three new columns, immutability amended to allow one-time corrective backfills); §8-A checklist (splitter + resolver + backfill run).

Revisit condition: if the reviewer or the agent surfaces recurring "same-person disambiguation" pain that a canonical person ID would fix (across CN + SMTP + bare display), reopen — the resolver's structured units are the natural input to a later identity clustering pass. If EDRM XML metadata is ever ingested (which carries directory info), reopen.

---

**Decision 2 — TEXT-JSON columns are `json.dumps`-encoded via `TextField`; migrating to `JSONField` proper is deferred.**

Options considered:
1. Migrate `to_addrs`, `cc_addrs`, `attachment_refs`, `raw_headers`, `*_display` to Django `JSONField` (cleaner: no manual encode/decode; SQLite JSON1 available for queries).
2. Keep `TextField` + `json.dumps` at write time and `json.loads` at read time (SELECTED).

Decision: Option 2. Fix `parse_document_file` to `json.dumps`-encode consistently; leave the column types as `TextField` for now.

Rationale: the live DB was built by an earlier json-dumping version, so existing rows are correct JSON strings and `read_document` was never actually broken in production; the regression only affects fresh clones. Migrating to `JSONField` is a mechanical change that adds no functional capability at demo scale, whereas fixing the encoding in-place is a one-line addition and unblocks fresh-clone correctness. The §6 shape description ("TEXT — JSON") stays exactly correct.

Spec edits (applied): §5 "Serialisation of TEXT-JSON columns" paragraph; §6 documents schema note; §6 code-conformance note (added "Resolved 2026-07-04" block).

Revisit condition: if any query needs SQLite JSON1 (indexed queries into a JSON payload, e.g. "find docs where any `to_display[i].cn_code == 'Sshackl'"), migrate the specific column to `JSONField` at that point. Currently all such lookups are Python-side after a coarser SQL filter, which is fine at 455k rows.

---

**Decision 3 — `check_privilege_signals` matches participants STRUCTURALLY (cn_code / email exact = high; display token-subset = low); `participants_unresolved` fires unless BOTH From AND To carry a matchable unit; `known_lawyers_in_*` shape changes from `[str]` to `[{name, via, matched}]`; strength weighting downgrades display-only matches.**

Options considered:
1. Keep the substring `_match_participants` — scan raw participant text for lawyer surnames. Simple, but blind to mis-splits and surname-collision-prone.
2. Structural match on the resolved units (SELECTED) — for each unit, check `cn_code` (exact, high confidence), then `email` (exact, high confidence), then `display` (`token_subset_match` against variants, low confidence). Precedence: exact wins over display across ALL lawyers.

Decision: Option 2.

Rationale: substring matching was breaking on the same 6,165 + 973 + 609 doc splitter defects Decision 1 fixes. With resolved units available, structural matching is not just possible but correct: an Exchange CN code is a person key; an email is a person key; a display token-subset is a heuristic and its confidence is honestly reflected in the audit trail (`via: "display"` vs `via: "cn_code"`).

The `participants_unresolved` semantics change ("unless BOTH From AND To carry ≥1 matchable participant", vs the previous "true only when both missing") deliberately raises the false-positive rate on the flag (~40% of docs now flag). This is aligned with the §3 stance: "no lawyer found" must not read as "not privileged." A field that is present but composed entirely of `x500_blank`/`other` units (undisclosed-recipients, suppression labels) is not usable evidence and shouldn't count.

The output shape change (`known_lawyers_in_*: [str]` → `[{name, via, matched}]`) is a break, but there are no consumers of the old shape today (verified: `prompts.py`, `loop.py`, and the React frontend have zero references). The new shape carries the audit trail the deterministic-and-defensible design demands.

Strength weighting refined: `weak` for display-only lawyer alone (surname-collision-prone), `moderate` for high-confidence participant alone or with one content signal, `strong` reserved for high-conf + two content signals or lawyer + external counsel + content. Prevents a bare-display match (potentially wrong person) from bumping the aggregate signal above the content evidence.

Spec edits (applied): §3 `check_privilege_signals` (PrivilegeSignals shape; structural matching paragraph; `participants_unresolved` refined semantics; strength weighting refined; address-matching reality reworked); §8-D checklist (marked done).

Revisit condition: if lawyer-list fill (`suggest_lawyer_cn_codes` output pasted into `lawyers.py`) produces many high-conf hits and the display-only tier becomes marginal, reconsider dropping the display tier entirely for higher precision. If corrections surface "this specific same-name person is NOT the lawyer" cases, add a per-lawyer exclusion list (rare in the demo).

---

**Decision 4 — Add `find_participant_documents` as a new §3 tool: scoped participant-name lookup over SQLite `*_display` columns. NOT canonical-identity resolution.**

Options considered:
1. Do nothing; when the reviewer or agent needs to trace a person, use `search_documents` with the name as a semantic query. **Rejected**: Chroma's semantic search matches body content, not participant metadata — a document from Shackleton discussing "swap agreements" will be found by a "swap" query, not by a "Shackleton" query, because the body may not mention her. This blurs the retrieval story.
2. Add a person-scoped structured lookup tool (SELECTED). Match query name tokens against `*_display[i].display` via `token_subset_match`; short-circuit against `email` (if query has `@`) or `cn_code` (if query is a lone identifier). Return the matching UNIT so the caller sees which form hit. No canonical person IDs — the reviewer adjudicates whether two hits are the same person.

Decision: Option 2. Full write-up in §3 `find_participant_documents`.

Rationale: the corrections mechanism (§2) requires that a correction naming a person can influence future documents involving that person. Without a person-scoped lookup, the agent can only apply such a correction opportunistically when the person happens to appear in the next document — and even then, it has to spot the person across three inconsistent address forms. `find_participant_documents` makes this a first-class capability, deterministically and without adding an identity registry the corpus can't support. It also fits the "structured vs semantic" separation: `search_documents` is Chroma over bodies, `find_participant_documents` is SQLite over participant units — two different questions, two different tools. Adjacent to but distinct from the cut `extract_entities` (that was LLM entity extraction over free text; this is deterministic person-scoped retrieval).

Match rule is `token_subset_match`, same primitive `check_privilege_signals` uses for lawyer display matching — one matcher for the codebase, no drift.

Spec edits (applied): §3 new `find_participant_documents` subsection (full write-up); §5 note on tool separation; §8-D TODO added; defer list updated to note `extract_entities` stays cut, superseded by this deterministic alternative.

Revisit condition: if the match rule (token-subset) proves too broad on common surnames (Jones, Cook, Moore, Davis all appear as counsel — see the Lawyer-list Pending resolution below), tighten with a "must-match" mode that requires at least two tokens. Feature-chat for the tool wrapper finalises the match rule and any surname disambiguation UX. If EDRM XML metadata is ever ingested, this tool can additionally query real Internet headers.

---



**Context.** Three decisions were reached in the `classify.py` and `privilege.py` feature
chats. Decisions 2 and 3 are implemented in code (verified: forced `record_judgment` in
classify.py; live signals + no `PrivilegeSignals` model in privilege.py). Decision 1's tool
is shaped for injection (classify_relevance still takes `criteria`) but the loop-side wiring
is **not yet built** — loop.py's TOOLS schemas are placeholders and tools/__init__.py's
dispatch still reads `args["criteria"]` (must fetch `AgentRun.criteria` via run_id instead;
see §8-C/D checklist note). The spec edits below should be applied in a Mode 1 pass; the
wiring lands when the loop is built.

---

**Decision 1 — The classification criterion is run-level config, injected by the loop, not supplied per-call by the orchestrator LLM.**

Options considered:
1. LLM supplies `criteria` on every `classify_relevance` call (as written in §3;
   dispatch reads `args["criteria"]`) — gives the orchestrator latitude to adapt or
   narrow the criterion.
2. The loop injects the run's canonical criterion (`AgentRun.criteria`); the LLM
   supplies only `doc_id`.

Decision: Option 2. Drop `criteria` from the classifier's LLM-facing tool schema;
the dispatch injects `AgentRun.criteria` via `run_id`. The Python function signature
`classify_relevance(doc_id, criteria)` is unchanged — only the caller changes.

Rationale: there is one topic per run (multi-topic is deferred), so the criterion is
a run constant — config, not a per-call decision. Re-emitting a fixed ~50-word string
every call invites drift and wastes tokens. The classifier is a separate, versioned
tool precisely so it can be evaluated independently (eval scores prompt v1 against the
TREC Topic 204 gold); if the orchestrator could mutate the criterion, v1 would no
longer be stable and the eval number would stop describing the classifier the cockpit
actually runs. Adaptation is already delivered through the orchestrator's corrections
channel (§2) and its retrieval/review/proposal agency — fixing the criterion removes
only criterion-mutation, which is the one bit of flexibility that is actively harmful.
Made explicit: the classifier is corrections-blind by design — reviewer corrections
act at the orchestrator/proposal layer, never inside `classify_relevance`.

Spec edits: §3 `classify_relevance` (add the "who supplies the criterion" note); §2
eval-mode line (parity is now "same prompt *and* same criterion"); §3 Flow 1
(`classify_relevance(doc_id)` — loop injects the criterion). `AgentRun.criteria` (§6)
already exists — no schema change.

Revisit condition: if multi-topic-per-run or sub-criterion refinement leaves the defer
list, or eval shows the classifier needs topic-specific narrowing that cannot live in
prompt v1, reconsider per-call criteria.

---

**Decision 2 — `classify_relevance` obtains structured output via a forced tool call, not by parsing JSON from free text.**

Options considered:
1. Prompt the model to emit JSON, then parse it (with a stricter-prompt retry on
   malformed output — the mechanism §3's Errors line describes).
2. Declare a `record_judgment` tool with the RelevanceJudgment schema and force it
   via `tool_choice`; read the tool_use block's `.input` (already a dict).

Decision: Option 2. Output is defensively coerced (confidence clamped to [0,1],
`key_passages` forced to a string list) but no fence-stripping or malformed-JSON retry
path exists.

Rationale: forcing the tool enforces the output shape up front, which is more robust
than post-hoc parsing and effectively removes the "malformed structured output" failure
mode. This is the correct reading of §3's intent even though it changes the mechanism.

Spec edit: §3 `classify_relevance` Errors line is stale ("malformed structured output
(retry with a stricter prompt, then error)") — update to reflect the forced tool call.

Revisit condition: if a future model or a non-Anthropic backend makes forced tool use
unavailable or unreliable, fall back to JSON-parse-with-retry.

---

**Decision 3 — `check_privilege_signals` computes all signals live at call time; the `privilege_signals` cache table is dropped from scope.**

Options considered:
1. Build the §6 `privilege_signals` cache model + populate participant signals during
   ingestion (as §3/§6 envisioned), tool reads cache + computes content/context live.
2. Compute everything (participant + content + context) live at call time; no cache.

Decision: Option 2, and drop the `privilege_signals` cache table. (Recommended; the
§3/§6 spec edits removing the cache should be applied in the Mode 1 pass.)

Rationale: the cache model was never built and ingestion never populated it. The tool
runs in milliseconds on a single document (a substring scan of one body + matching a
handful of participants against ~10 lawyers), so precomputing participant signals is an
optimization with no demo-scale payoff and real dependency cost (a model, a migration,
ingestion coupling). If the cache is ever wanted for scale, `_compute_signals` is
exactly the logic ingestion would run.

Spec edits: §3 `check_privilege_signals` (note signals are computed live); §6 (remove
the `privilege_signals` cache table, or mark it explicitly deferred).

Revisit condition: if privilege triage becomes a measured throughput bottleneck at
larger scale (many thousands of live reviews), reintroduce the cache.

---

# Decisions Pending

_Not yet decided. Recorded here so the open questions and their couplings are not lost
between sessions. To be resolved in a Mode 1 (Architecture) chat._

**RESOLVED 2026-07-04 — General alias → canonical-identity resolution.**

Resolved by the 2026-07-04 entry above (Decisions 1 + 4). Summary of what was chosen and
why the framing shifted:
- **Structured display units on `Document`, not a canonical person ID or a corpus-wide
  registry.** Each unit carries `{raw, display, kind, cn_code, email, domain}`; two units
  are "the same person" by equality on `cn_code` or `email` (deterministic), or by
  reviewer judgement on display (adjudicated, not automated). The rev-3 CN registry cut
  is reinforced — the participant-format survey found exactly one `x500_blank` unit
  corpus-wide, so a lookup table would recover nothing that isn't already sitting next
  to the DN.
- **`extract_entities` stays cut.** The "find people" need that motivated reopening is
  served by `find_participant_documents` (Decision 4) — deterministic structured lookup
  over the resolved units, not LLM entity extraction over free body text.
- **UI consistency achieved via `display` field on the resolved unit** (§4).
- **Corrections-identity achieved via structural matching in `check_privilege_signals`
  (Decision 3) + `find_participant_documents` (Decision 4).** The agent can apply a
  correction naming a person to future documents by structural match, without a
  canonical ID.

Feasibility note that had been recorded here (CN codes and display names are inline in
the DN, so a corpus scan pairs them without a directory) stood up — implemented as
`manage.py suggest_lawyer_cn_codes`.

---

**RESOLVED 2026-07-04 (partially) — Lawyer-list scope: ~10 custodians vs broader roster.**

Partially resolved by the 2026-07-04 entry above. The hard part — CN codes cannot be
guessed and needed manual grep — is now automated by `manage.py suggest_lawyer_cn_codes`
(mines candidates from resolved `x500_named` units, prints them with hit counts and a
surname-collision warning for eyeball). Expansion beyond the 10 §5 custodians is now
cheap: the same command surfaces CN codes for any surname added to `LAWYERS`.

Still to decide (deferred to the lawyer-list feature chat, "Chat C"):
- Which non-custodian counsel to add (Jordan Mintz / Rex Rogers / broader roster).
- Verification fixes already identified: "Jones" is ambiguous (Karen Jones, AGC
  Portland, vs custodian Tana Jones); Shackleton / Nemec / Heard unverified; Haedicke,
  Sager, Mann, Sanders, Taylor, Derrick (James V.) confirmed. External counsel: Vinson
  & Elkins (velaw.com) confirmed; Andrews & Kurth to add; NOT Alston & Bird (bankruptcy
  examiner, not Enron counsel).

Where decided: Chat C. The resolver + suggest command make this a data task now, not an
identity-resolution problem.



## 2026-07-02 — Corpus re-confirmed; evaluation methodology fixed; plan recompressed to 2 days
 
**Context.**
Two days remain (was 3.5). Nothing is built yet; qrels not downloaded. The corpus
decision was explicitly re-opened by the team ("prefer restarting with a
straightforward extraction plan than fighting messiness, if an alternative fits").
The spec's biggest gap was that "evaluate on the assessed pool" never specified how
the agent runs over it — the exact class of eval-day surprise the revision-2 pivot
was meant to eliminate. Verification pass run against primary TREC sources (official
TREC 2010 overview PDF; NIST-hosted qrels page, readme, `dolegal10eval.sh`,
`calc2.c`) before deciding anything.
 
**Verified facts (primary sources).**
1. `qrels.t10legallearn.gz` exists at trec.nist.gov/data/legal/10/ (mirror at UMD
   legal10-results). 97MB gz ⇒ one row per document per topic (5.48M rows), not
   judgments only. Format inferred from the official toolkit: join key
   `topic:docid`; stratum ∈ {100, 1000, 10000, 1000000}; rel ∈ {−1 unjudged,
   0 non-relevant, 1 relevant}. Columns to be confirmed on download (Day-1 hour 1).
2. Doc-id format in the toolkit's own example (`3.1131864.J0J3...`) = on-disk
   filename stem. Join holds by construction.
3. Gold standard: stratified sample ~2,720 docs/topic, 3 law-trained assessors,
   majority vote. ~1.25% of docs coded "broken" — corroborates our ~1.7% observed
   binary corruption.
4. Topic 204 estimated relevant = 6,362 (hardcoded 6361.83 in official calc2.c). ✓
5. **Correction to the 2026-07-01 entry:** "≈50% recall at a 3% cut" was the best
   run's cross-topic AVERAGE. On Topic 204 specifically: best recall at the 3% cut
   was 29.8%; best actual F1 on 204 was 26.0% (best hypothetical 26.6%). Topic 204
   was among the hardest 2010 topics. Strengthens the honest-numbers framing;
   forbids same-axis comparisons with TREC systems.
6. `seed.csv` in data/raw ≙ the Learning-task seed set. Topic 204: 59 relevant +
   1,132 non-relevant = 1,191 labelled docs (overview Table 2). Available now,
   before qrels download. `docids-v2.csv.bz2` = canonical doc-id↔SDOC map;
   `msg-uniqmsg` / `uniqmsg` = duplicate maps (usable as ingestion integrity
   checks).
7. EDRM v2 XML edition carries threading info and Internet headers (ZL/EDRM launch
   materials) — the text bundle's missing Message-ID/addresses is a rendering
   artifact, not a corpus property. XML is ~74GB.
8. Privilege ground truth exists: Interactive-task Topic 304 message-level qrels
   (`qrel_leg_int_2010_msg_post.txt`, small plain-text, NIST legal10 page).
**Decision 1 — Corpus: stay on EDRM v2 text bundle + Topic 204 (re-opened, re-closed).**
Options considered:
- A. Stay (SELECTED). Extraction is a solved problem: DATA_REFERENCE.md reduces the
  loader to seven deterministic rules; ~150-line parser. Messiness is rewarded by
  the brief ("the bigger and messier, the better the story") and becomes demo
  material (defensive loader, participants_unresolved flag).
- B. CMU/CALO maildir. Clean headers, but no ground truth mapping exists (TREC's own
  statement, re-confirmed). Kills the benchmark = kills the defensibility spine
  (Technical 35% + Impact 30%). Rejected.
- C. EDRM v2 XML. Recovers threading/addresses but ~74GB: download + parse burns a
  day of two, and disk comfort is limited. Rejected; recorded as the production
  ingest path in future work.
- D. Other labelled corpora (e.g. TREC Total Recall / Jeb Bush emails). Would
  restart the entire data investigation under time pressure with uncertain current
  availability. Rejected.
**Decision 2 — Evaluation methodology: two separate honest metrics; eval decoupled from full ingestion.**
Options considered:
- (a) Headless classification of the judged pool. Clean number; doesn't test search;
  needs an explicit gate-bypass story.
- (b) Full agentic run over the corpus, score touched docs. Recall structurally tiny
  (agent reviews hundreds of 455K; ~6,362 relevant exist); number misleadingly bad.
- (c) SELECTED — hybrid:
  Metric 1 (accuracy): headless **eval mode** — `classify_relevance` (Haiku, prompt
  v1) over judged Topic-204 base emails read straight from disk; recall-first
  report "on the assessed gold sample, N docs." Plan A = full pool (~£5–7, gated by
  a 50-doc cost pilot); Plan B = all judged-relevant + fixed-seed non-relevant
  sample, exact recall + derived precision-in-pool. Bypassing human gates is
  legitimate because eval mode measures the classifier; nothing commits.
  Metric 2 (impact): measured docs/hour throughput (eval concurrency + live loop);
  deck projections derive only from measured quantities.
  Explicit non-claim: end-to-end collection recall (different quantity from TREC's
  ranked-retrieval recall; same-axis comparison would be an own-goal).
  Seed hygiene: seeds never in prompts; used for dev sanity checks + demo doc
  selection; seed/qrels overlap excluded from reported metrics.
Rationale: kills the last "uncomputable on eval day" risk (format known in advance,
counts verified hour 1); the accuracy number survives an embedding-run failure;
budget fits the £10–15 envelope with a pilot gate.
**Decision 3 — 2-day plan; cuts anchored to judging weights.**
Submission is repo + deck + recorded video ⇒ the recording is the deliverable
(retakes allowed); hard stop building ~20:00 Day 2, then video → deck → README.
Additional cuts beyond the revision-2 defer list: `find_thread` cut entirely; audit
query bar cut (also resolves the §4/§8 contradiction); CN→display-name corpus map
cut (lawyer list hand-carries CN codes for ~10 known counsel — several custodians
were Enron lawyers: Haedicke, Shackleton, Sager, Sanders, Mann, Taylor, Jones,
Nemec); reversal demoted to stretch; pause/resume UI cut (schema keeps resumability).
Never cut: qrels join + eval, corrections flow + corrections viewer, batch approval
gates, reasoning stream — these carry Technical (35%), Control (20%), Demo (20%),
and the eval underwrites Impact (30%).
 
**Revisit conditions.**
- Day-1 hour-1: if qrels columns differ from the inferred format, adapt the parser
  (the eval toolkit source is the reference); if judged-relevant base emails for
  204 < ~150, execute the Topic 202 fallback the same day.
- If the 50-doc pilot shows per-doc cost >2× estimate, switch to Plan B immediately.
- If `seed.csv` is not the seed set (schema check hour 1), lose nothing — it was an
  accelerator, not a dependency.
- If overnight full-corpus embedding fails, demo on the ingested subset and state
  the actual count on the slide; do not delay the eval, which doesn't depend on it.


## 2026-07-01 — Corpus & evaluation ground truth: CMU/CALO → EDRM v2 text bundle; topic → TREC 204

**Context.**
Original spec (§5) ingested the CMU/CALO Enron maildir (~500K messages) and
scored agent relevance decisions against TREC Legal Track 2010 qrels, treating
doc-id alignment as a ~30-min "normalisation step." Demo (§7) was framed on
"Topic 207 = Special Purpose Entity transactions," with Topic 206 (Chewco/
Fastow) as backup. The recall/precision number is the pitch's defensibility
spine.

**Issue discovered (before building — verified against primary TREC sources
and direct disk inspection).**
1. No cross-corpus mapping exists. The qrels key to the EDRM collection, NOT to
   CMU/CALO; TREC itself lists "the lack of a mapping between this collection
   and other Enron email collections" as a known shortcoming. The planned
   normalisation rested on a crosswalk that does not exist.
2. Topic numbers were wrong. Verified from the TREC 2009 overview: 201=prepay,
   202=FAS 140/125, 203=financial forecasts, 204=document destruction/
   retention, 205=energy schedules/bids, 206=analyst communications,
   207=fantasy football. There is NO SPE/Chewco/LJM topic. The demo's central
   framing was built on a misremembered topic.
3. Consequence: the planned metric could not have been computed against the
   ingested corpus — discoverable only on eval day, or worse, yielding a
   true-looking but meaningless number.

**Options considered.**
- A. Stay on CALO + hand-label ~100–200 docs. Rejected: manual effort blows the
     timeline; loses external credibility; discards the real benchmark.
- B. Stay on CALO + fuzzy-map qrels across collections. Rejected: research-grade
     effort; TREC states the mapping doesn't exist.
- C. Ingest full EDRM (~74GB XML / ~100GB PST). Rejected as framed: download/
     parse/storage blows the timeline; drags attachment handling (a cut feature)
     back into scope.
- D. EDRM v2 de-duplicated 596MB TEXT bundle + real qrels, eval on the assessed
     pool, topic 204. SELECTED.

**Decision.**
1. Corpus: drop CMU/CALO. Use the EDRM Enron v2 de-duplicated text-rendering
   bundle (`edrmv2txt-v2.tar.bz2`, 596MB → 685,592 .txt documents on disk =
   455,449 canonical messages + 230,143 attachments; matches the official TREC
   2010 collection count exactly). Ingest email messages as the searchable
   haystack; no per-custodian selection.
2. Evaluation: score against the TREC 2010 Learning-task gold standard
   (`qrels.t10legallearn`), which keys to the same doc-ids as the on-disk
   filenames (join verified: 471/471 on a Topic-204 sample). TREC judged a
   stratified sample (~2,720 docs/topic, 3 assessors, majority vote), so
   evaluate on the assessed pool (both responsive and non-responsive present),
   restricted to base-email doc-ids. Report as "on the Topic 204 assessed
   gold sample," NOT as an official weighted population estimate.
3. Demo topic: Topic 204 — documents relating to the destruction, retention,
   deletion, or shredding of evidence. Chosen over 201 (prepays) / 202 (FAS
   140) because it needs no finance/accounting knowledge to follow, is a vivid
   spoliation story, keeps privilege thematically central (legal-hold
   instructions from counsel), and has a healthy gold pool (~6,362 estimated
   relevant documents in the collection). Original SPE framing retired.
4. Attachments: remain out of scope (defer list preserved). Attachment doc-ids
   carry a `.1`/`.2` suffix, so filtering both ingest and eval to base-emails
   is a trivial string rule.
5. Metric framing (§7): lead with recall + human-in-the-loop, not a high F1.
   TREC 2010's best systems scored modestly on 204 (≈50% recall at a 3% cut;
   low-20s F1); a placeholder F1 of 0.83 is not credible against this benchmark
   and would invite a damaging question. Report honest numbers on the assessed
   pool; carry the pitch on recall and throughput.

**Rationale.**
Resolves the mapping problem at root — EDRM is the corpus the qrels were built
on, so alignment is by construction. Preserves both pitch pillars: scalability/
throughput (agent runs over the full corpus) and a credible accuracy number
(real TREC judgments, zero manual labelling). Smaller/simpler to ingest than
CALO (596MB pre-extracted, de-duplicated text vs a 1.4GB maildir needing
encoding-hell parsing). Topic 204 is legible to a non-technical judge.

**Revisit condition.**
- Address resolution: EDRM text renders internal participants inconsistently
  (clean SMTP / Exchange X.500 CN= / bare display name) with no directory table
  shipped in the corpus. If DATA_REFERENCE.md confirms CN= is not resolvable
  from the files alone, check_privilege_signals must match on name + CN= + email
  aliases (lawyer list carries all three forms per person); a corpus-scan alias
  bootstrap is an optional enhancement. FINALISE once DATA_REFERENCE.md lands.
- Threading: EDRM text has no Message-ID/In-Reply-To header. find_thread must
  rely on normalised-subject + participant overlap only — demoted from
  "reliable" to "best-effort." Confirm against DATA_REFERENCE.md.
- If Topic 204's assessed gold pool proves too small/skewed once qrels.
  t10legallearn is counted, fall back to Topic 202 (FAS 140).