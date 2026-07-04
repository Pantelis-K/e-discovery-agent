"""
Headless evaluation mode (spec Sec.2 "Eval mode (headless)", Sec.8-G).

Classifies Topic-204 judged base emails through the SAME classify_relevance
tool the cockpit uses (Haiku, prompt v1, run-level criterion) and records each
proposed decision as a Decision row under an AgentRun with run_type="eval".
Never commits - Decision.committed stays False forever, because eval measures
the classifier, not a reviewed determination (spec Sec.2).

No orchestrator, no Chroma, no human gates. Does NOT depend on full-corpus
ingestion: each document is read from SQLite if already there (it will be, if
`manage.py ingest_documents` has run), otherwise parsed on demand straight from
data/raw/ via doc_id_index.json and upserted as a Document row - only the
judged doc-ids need to be readable on disk for eval to work (spec Sec.2).

Resumable: doc-ids that already have a Decision under the target run_id are
skipped, so a crash or a rate-limit stall costs nothing to re-run.

Usage (from backend/):
    python run_eval.py                     # Plan A: full judged pool (~2,028 docs)
    python run_eval.py --pilot 50          # 50-doc cost/latency pilot (Sec.8-G)
    python run_eval.py --plan b            # Plan B: all relevant + fixed non-relevant sample
    python run_eval.py --run-id my-eval-1  # resume / name the run explicitly
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_discovery_backend.settings")

import django  # noqa: E402

django.setup()  # noqa: E402

from django.utils import timezone  # noqa: E402

from agent.models import AgentRun, Decision  # noqa: E402
from agent.prompts import CLASSIFICATION_PROMPT_VERSION, TOPIC_204_CRITERIA  # noqa: E402
from agent.tools.classify import classify_relevance  # noqa: E402
from documents.models import Document  # noqa: E402
from documents.parsing import parse_document_file  # noqa: E402
from eval_gold import load_gold_204  # noqa: E402

CONCURRENCY = 5              # spec Sec.2: tier-1 input-token limits are the binding constraint
PLAN_B_SAMPLE_SIZE = 400     # non-relevant docs sampled alongside all relevant ones
PLAN_B_SEED = 204            # fixed seed -> reproducible Plan-B sample across runs


def select_doc_ids(gold: dict[str, int], plan: str, sample_size: int) -> list[str]:
    if plan == "a":
        return sorted(gold)
    relevant = sorted(d for d, r in gold.items() if r == 1)
    nonrelevant = sorted(d for d, r in gold.items() if r == 0)
    sample = random.Random(PLAN_B_SEED).sample(nonrelevant, min(sample_size, len(nonrelevant)))
    return sorted(relevant + sample)


def ensure_document(doc_id: str, doc_index: dict, data_raw: Path) -> str | None:
    """Returns None on success, or an error string. Upserts a minimal Document
    row from disk if one isn't already in SQLite (spec Sec.2 eval decoupling)."""
    if Document.objects.filter(pk=doc_id).exists():
        return None
    rel_path = doc_index.get(doc_id)
    if rel_path is None:
        return f"doc_id not in doc_id_index.json: {doc_id}"
    file_path = data_raw / rel_path
    try:
        raw = file_path.read_bytes()
    except OSError as e:
        return f"cannot read {file_path}: {e}"
    parsed = parse_document_file(raw, doc_id, str(file_path))
    if parsed is None or "__skip__" in parsed:
        reason = (parsed or {}).get("__skip__", "parse returned None")
        return f"skipped ({reason})"
    Document.objects.create(**parsed)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", default=None, help="Eval run_id (default: derived from --plan/--pilot)")
    parser.add_argument(
        "--plan", choices=["a", "b"], default="a",
        help="a = full judged pool, b = relevant + fixed non-relevant sample (Sec.8-G Plan A/B)",
    )
    parser.add_argument("--plan-b-sample", type=int, default=PLAN_B_SAMPLE_SIZE)
    parser.add_argument(
        "--pilot", type=int, default=None,
        help="Classify only the first N selected doc-ids (Sec.8-G 50-doc pilot gate)",
    )
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--data-root", default=None, help="Corpus root (default: <repo_root>/data/raw)")
    args = parser.parse_args()

    data_raw = Path(args.data_root) if args.data_root else (REPO_ROOT / "data" / "raw")

    gold = load_gold_204(data_raw)
    doc_ids = select_doc_ids(gold, args.plan, args.plan_b_sample)
    if args.pilot:
        doc_ids = doc_ids[: args.pilot]

    run_id = args.run_id or (f"eval-pilot-{args.pilot}" if args.pilot else f"eval-plan-{args.plan}-204")

    run, created = AgentRun.objects.get_or_create(
        run_id=run_id,
        defaults=dict(
            run_type="eval",
            topic="204",
            criteria=TOPIC_204_CRITERIA,
            status="running",
            batch_size=len(doc_ids),
        ),
    )
    if not created and run.run_type != "eval":
        sys.exit(f"refusing to reuse run_id {run_id!r}: run_type={run.run_type!r} (expected 'eval')")

    done = set(Decision.objects.filter(run_id_id=run_id).values_list("doc_id_id", flat=True))
    todo = [d for d in doc_ids if d not in done]
    print(
        f"run_id={run_id} plan={args.plan} prompt={CLASSIFICATION_PROMPT_VERSION} "
        f"selected={len(doc_ids)} already_done={len(done)} todo={len(todo)}"
    )
    if not todo:
        print("nothing to do.")
        return

    doc_index = json.loads((data_raw / "doc_id_index.json").read_text(encoding="utf-8"))

    ready = []
    for doc_id in todo:
        err = ensure_document(doc_id, doc_index, data_raw)
        if err:
            print(f"  ! {doc_id}: {err}")
            continue
        ready.append(doc_id)

    total_in = total_out = ok = errors = 0
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(classify_relevance, doc_id, TOPIC_204_CRITERIA): doc_id
            for doc_id in ready
        }
        for i, future in enumerate(as_completed(futures), 1):
            doc_id = futures[future]
            result = future.result()
            if "error" in result:
                errors += 1
                print(f"  ! {doc_id}: {result['error']}")
                continue
            usage = result.pop("_usage", {})
            total_in += usage.get("input_tokens", 0)
            total_out += usage.get("output_tokens", 0)
            Decision.objects.create(
                run_id_id=run_id,
                doc_id_id=doc_id,
                proposed_by="agent",
                relevance=result["relevant"],
                privilege="unclear",   # eval scores Metric 1 (responsiveness) only
                issue_tags=[],
                confidence=result["confidence"],
                reasoning=result["reasoning"][:8000],
                committed=False,       # eval never commits (spec Sec.2)
            )
            ok += 1
            if i % 25 == 0 or i == len(ready):
                elapsed = time.monotonic() - start
                rate = i / elapsed * 60 if elapsed else 0
                print(
                    f"  {i}/{len(ready)}  ok={ok} err={errors}  "
                    f"tok_in={total_in} tok_out={total_out}  "
                    f"{elapsed:.0f}s elapsed  ~{rate:.0f} docs/min"
                )

    run.status = "completed"
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at"])

    print(f"\ndone. ok={ok} errors={errors} tokens_in={total_in} tokens_out={total_out}")
    print(f"next: python report_eval.py --run-id {run_id}")


if __name__ == "__main__":
    main()
