# Data download (for windows)
```bash
mkdir data\raw
cd data\raw

# 1. The corpus: de-duplicated text rendering, ~596MB

curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/edrmv2txt-v2.tar.bz2

# 2. Labelled data + ID files (all small)

curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/seed.csv
curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/docids-v2.csv.bz2
curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/uniqmsg.csv.bz2
curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/msg-uniqmsg.csv.bz2
curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10-results/qrels.t10legallearn
curl.exe -L -O https://trec-legal.umiacs.umd.edu/corpora/trec/legal10-results/readme.txt

# extract
tar -xf edrmv2txt-v2.tar.bz2

# get meta data
python run_eval.py #gives you judged_204.txt
python build_index.py #gives you doc_id_index.json
python compute_overlap.py #gives you overlap_excluded.txt
```


# Dataset Files


## `qrels.t10legallearn`

The TREC 2010 Legal Track Learning-task evaluation set. Documents were pooled from the top-ranked results of every participating team's submission (plus random draws), then each pooled document was assessed by three law-trained reviewers per topic and resolved by majority vote.

### Format

Plain text, space-separated, three columns per row, one row per `(topic, document)` pair.

| Column | Description |
|--------|-------------|
| `topic:docid` | Colon-joined topic number and canonical doc-id (matches on-disk filename stems). |
| `stratum` | Sampling stratum for the population estimate. One of `{100, 1000, 10000, 1000000}`. |
| `rel` | Assessor judgment: `-1` = unjudged, `0` = non-relevant, `1` = relevant. |

### Provenance

Downloaded from <https://trec-legal.umiacs.umd.edu/corpora/trec/legal10-results/qrels.t10legallearn.gz> (UMD mirror of the TREC NIST release), then gunzipped in place.

### Usage

Source of ground truth for **Metric 1 (classification accuracy)**.

`judged_204.txt` is derived from this file.

---

## `seed.csv`

The TREC 2010 Learning-task training seed set. A small curated set of pre-labelled examples per topic, distributed to participants before the competition so they could train classifiers before running on the full corpus.

### Format

CSV, comma-separated, four columns, **no header row**, one row per `(document instance, topic)` pair.

Attachments appear as separate rows with a per-attachment content hash in column 1 and a `.N` suffix in column 4.

| Column | Description |
|--------|-------------|
| `hash_extended_docid` | Canonical doc-id with an attachment-content hash appended when the row is an attachment; otherwise identical to column 4. |
| `topic` | TREC topic number (`200–207` in this file). |
| `label` | Assessor judgment: `0` = non-relevant, `1` = relevant. |
| `canonical_docid` | Canonical TREC doc-id (join key with qrels and on-disk filenames). |

### Provenance

Distributed with the TREC 2010 Learning-task materials; present at `data/raw/seed.csv` in the corpus bundle.

### Usage

- Development sanity checks against known-labelled documents.
- Demo-document selection (vivid relevant examples for the video).
- **Never** injected into prompts.

Doc-ids appearing in both `seed.csv` and `judged_204.txt` are excluded from Metric 1 (see `overlap_excluded.txt`).

---

## `judged_204.txt`

Canonical doc-ids of Topic 204 judged base emails — the concrete evaluation set for Metric 1.

### Format

Plain text, one canonical doc-id per line, **no header**.

### Provenance

Derived from `qrels.t10legallearn` by `count_204.py`:

- Filtered to `topic == 204`
- Kept only `rel ∈ {0, 1}`
- Dropped doc-ids with a `.N` attachment suffix

### Usage

- Evaluation pool for `run_eval.py` (classify each document and score against the qrel labels).
- Priority list for `ingest.py` (the development subset must include every doc-id in this file, otherwise there is nothing to score against).

---

## `doc_id_index.json`

Master lookup from canonical doc-id to filesystem path for every base email on disk.

### Format

Single JSON object:

```json
{
  "doc_id": "filesystem_path",
  ...
}
```

One entry per base email.

### Provenance

Built by `build_index.py` walking:

```
data/raw/*.zip/text_NNN/*.txt
```

(globbing `*.zip` directories, per the §5 enumeration rule), excluding `.N`-suffixed attachment files.

### Usage

- Consumed by `ingest.py` to enumerate what to load.
- Used by `run_eval.py` to resolve judged doc-ids to file paths without re-walking the directory tree.
- Used by the review-state filter in `search_documents` for existence checks.

---

## `overlap_excluded.txt`

Doc-ids that appear in both `seed.csv` (Topic 204 base rows) and `judged_204.txt`.

Regardless of label agreement, **membership in the seed set is the disqualifying condition**, not label agreement.

### Format

Plain text, one canonical doc-id per line, **no header**.

### Provenance

Computed by `compute_overlap.py` as the set intersection of:

- Topic 204 base doc-ids in `seed.csv`
- Doc-ids in `judged_204.txt`

### Usage

Read by `report_eval.py` and subtracted from the evaluation set before computing recall and precision.

This implements the **seed-hygiene rule**: a document that was available as a labelled training example, however lightly used, cannot be included when honestly evaluating the agent.