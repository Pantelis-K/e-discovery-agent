# Decision Log

Entries follow the format (ordered most recent to least):
**Date | Decision title**
- Context:
- Options considered:
- Decision:
- Rationale:
- Revisit if:

## 2026-07-03 — Feature-chat decisions: run-level criterion, forced classify tool use, live privilege signals

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

**PENDING — General alias → canonical-identity resolution (reopens two cut decisions).**

Decision to be made: whether to build a resolver that maps any participant form (clean
SMTP, X.500 DN / bare `CN=CODE`, bare display name) to a single canonical identity, and
in what form — a bounded/lazy resolve-at-read-time approach (resolve only participants
in reviewed documents) versus a precomputed corpus-wide registry table.

This reopens explicitly cut decisions and must be treated as a reopen, not a fresh idea:
`extract_entities` (cut revision 1, "the agent rarely needs entity extraction") and the
corpus-wide `CN → display-name` map (cut revision 3, on the 2-day budget).

New information not weighed at cut time (the justification to reopen):
- UI consistency — the reviewer's to/from/cc panel should show uniform canonical names,
  not a mix of emails, X.500 DNs, and bare display names. (Stronger than the rev-1
  framing of "nicer display.")
- Corrections-identity (agent-facing, not anticipated by the rev-1 cut) — a correction
  names a person ("Person A is a lawyer but does not hold privilege"); the agent, reading
  a document where that person appears as a CN code or email, must resolve alias →
  identity to apply the guidance. This is a genuine agent-path requirement.
- It subsumes the lawyer-alias-finding work (see the coupled pending item below).

Feasibility note for the decision: X.500 DNs carry the display name in the prefix
(`Name </…CN=CODE>`), so a corpus scan pairs CN codes ↔ display names directly — the
absent corpus directory is not a blocker. The rev-3 cut was a budget call, not an
infeasibility one.

Depends on:
- The 2-day build budget — is it worth ~half a day of the two?
- Whether identity is needed at read-time (agent path, harder) or only at display-time
  (UI path, cheaper) — the corrections requirement pushes toward read-time.
- Bounded/lazy vs full precomputed registry.

Affects:
- `read_document` — does it return a canonical identity alongside raw participants?
- The corrections mechanism — how corrections reference and resolve people.
- The UI active-document panel (§4 display).
- `lawyers.py` — lawyer aliases become a byproduct of the resolver rather than a
  separate manual grep.
- The status of the two cut items (`extract_entities`, `CN → display-name` map).

Where decided: Mode 1 / "Chat A". Produces a spec amendment + a full decisions.md entry.

---

**PENDING — Lawyer-list scope: ~10 custodians vs broader roster.**

Decision to be made: keep the ~10 §5 lawyer-custodians, or expand — add prominent
non-custodian in-house counsel (e.g. Jordan Mintz, GC of Enron Global Finance; Rex
Rogers, VP & Associate GC), and/or move toward the full legal roster (Enron's legal
department ran to dozens of attorneys).

Depends on: the identity-resolver decision above. With a resolver + alias map,
expanding is cheap and low-risk; without it, expansion is manual grep plus false-positive
risk on common surnames (e.g. "Cook", "Moore", "Davis" all appear as counsel).

Affects: `check_privilege_signals` recall vs precision; the fill/verify work in
`lawyers.py`. Also carries verification fixes already identified: "Jones" is ambiguous
(Karen Jones, AGC Portland, vs custodian Tana Jones — confirm which, and whether an
attorney); Shackleton / Nemec / Heard unverified; Haedicke, Sager, Mann, Sanders,
Taylor, Derrick (James V.) confirmed. External counsel: Vinson & Elkins (velaw.com),
Andrews & Kurth (add domain); not Alston & Bird (bankruptcy examiner, not Enron counsel).

Where decided: coupled to Chat A (resolver); finalized in the lawyer-list feature chat
("Chat C").



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