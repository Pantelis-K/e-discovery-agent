"""
Shared gold-standard loading for eval mode (spec Sec.2 "Eval mode", Sec.8-G).

Both run_eval.py (what to classify, optional Plan-B stratified sample) and
report_eval.py (what to score against) need the same Topic-204 judged pool and
the same seed-hygiene exclusion set. One place to parse qrels.t10legallearn so
the two scripts can never quietly diverge on which doc-ids count.
"""

from __future__ import annotations

from pathlib import Path

TOPIC = 204
_TOPIC_PREFIX = f"{TOPIC}:"


def _is_attachment(doc_id: str) -> bool:
    """Attachment doc-ids carry a trailing '.N' segment (spec Sec.5); base
    emails only are in scope for ingestion and eval."""
    segs = doc_id.split(".")
    return len(segs) >= 4 and segs[-1].isdigit()


def load_gold_204(data_raw: Path) -> dict[str, int]:
    """doc_id -> rel (0 non-relevant, 1 relevant) for Topic 204 judged base
    emails. Mirrors data/raw/count_204.py exactly: topic 204, rel in {0, 1},
    attachment doc-ids dropped."""
    qrels_path = data_raw / "qrels.t10legallearn"
    gold: dict[str, int] = {}
    with qrels_path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) != 3:
                continue
            key, _stratum, rel = parts
            if not key.startswith(_TOPIC_PREFIX):
                continue
            rel_i = int(rel)
            if rel_i not in (0, 1):
                continue
            doc_id = key.split(":", 1)[1]
            if _is_attachment(doc_id):
                continue
            gold[doc_id] = rel_i
    return gold


def load_overlap_excluded(data_raw: Path) -> set[str]:
    """Doc-ids in both seed.csv and the judged pool (spec Sec.5 seed-hygiene
    rule) - excluded from reported Metric 1 regardless of label agreement."""
    path = data_raw / "overlap_excluded.txt"
    return {
        line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    }
