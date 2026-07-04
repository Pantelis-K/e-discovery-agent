"""
report_eval.py - Metric 1 (accuracy) from an eval run's Decision rows, scored
against the TREC 2010 Learning-task gold standard for Topic 204 (spec Sec.2
Eval mode, Sec.8-G). Companion to run_eval.py, which produces the Decision
rows this script reads.

Applies the seed-hygiene rule (spec Sec.5): doc-ids in both seed.csv and the
judged pool (overlap_excluded.txt) are subtracted before scoring, regardless
of label agreement.

Also reports the ~89.7% recall-ceiling footnote for the results slide: some
gold-relevant docs are empty/header-only and cannot be judged responsive by
the classifier (prompt v1's explicit rule for empty bodies) - that is a
structural ceiling on achievable recall, not a classifier failure.

Writes results.json and prints the same numbers to stdout.

Usage (from backend/):
    python report_eval.py --run-id eval-plan-a-204
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_discovery_backend.settings")

import django  # noqa: E402

django.setup()  # noqa: E402

from agent.models import Decision  # noqa: E402
from documents.models import Document  # noqa: E402
from eval_gold import load_gold_204, load_overlap_excluded  # noqa: E402


def recall_ceiling(relevant_doc_ids: set[str]) -> dict:
    bodies = dict(
        Document.objects.filter(doc_id__in=relevant_doc_ids).values_list("doc_id", "body")
    )
    total = len(relevant_doc_ids)
    empty = sum(
        1 for doc_id in relevant_doc_ids if not (bodies.get(doc_id) or "").strip()
    )
    achievable = total - empty
    return {
        "gold_relevant_total": total,
        "gold_relevant_empty_or_missing_body": empty,
        "achievable_relevant": achievable,
        "recall_ceiling": round(achievable / total, 4) if total else None,
    }


def evaluate(run_id: str, data_raw: Path) -> dict:
    gold = load_gold_204(data_raw)
    overlap = load_overlap_excluded(data_raw)
    eval_pool = {d: rel for d, rel in gold.items() if d not in overlap}

    predictions = dict(
        Decision.objects.filter(run_id_id=run_id, doc_id_id__in=eval_pool.keys())
        .values_list("doc_id_id", "relevance")
    )

    tp = fp = fn = tn = 0
    missing = []
    for doc_id, rel in eval_pool.items():
        if doc_id not in predictions:
            missing.append(doc_id)
            continue
        gold_relevant = rel == 1
        predicted = predictions[doc_id]
        if gold_relevant and predicted:
            tp += 1
        elif gold_relevant and not predicted:
            fn += 1
        elif not gold_relevant and predicted:
            fp += 1
        else:
            tn += 1

    scored = tp + fp + fn + tn
    recall = tp / (tp + fn) if (tp + fn) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None

    relevant_ids = {d for d, r in eval_pool.items() if r == 1}

    return {
        "run_id": run_id,
        "topic": 204,
        "judged_base_emails": len(gold),
        "seed_overlap_excluded": len(overlap),
        "eval_pool_size": len(eval_pool),
        "scored": scored,
        "missing_decisions": len(missing),
        "missing_doc_ids_sample": missing[:20],
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "recall": round(recall, 4) if recall is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "recall_ceiling_footnote": recall_ceiling(relevant_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", required=True, help="The eval run_id written by run_eval.py")
    parser.add_argument("--data-root", default=None, help="Corpus root (default: <repo_root>/data/raw)")
    parser.add_argument("--out", default=str(BACKEND_DIR / "results.json"))
    args = parser.parse_args()

    data_raw = Path(args.data_root) if args.data_root else (REPO_ROOT / "data" / "raw")

    results = evaluate(args.run_id, data_raw)
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(json.dumps(results, indent=2))
    print(f"\nwrote {args.out}")

    if results["missing_decisions"]:
        print(
            f"\nNOTE: {results['missing_decisions']} judged doc-ids have no decision yet "
            f"under run_id={args.run_id} - re-run run_eval.py --run-id {args.run_id} to finish "
            f"them before treating these numbers as final.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
