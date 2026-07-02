"""
Django management command: ingest EDRM base emails into the Document model.

Run via manage.py from the backend/ directory:

    # Dev subset (Day 1 morning):
    python manage.py ingest_documents \
        --include ../data/raw/judged_204.txt \
        --custodians dasovich-j germany-c beck-s

    # Full corpus (overnight):
    python manage.py ingest_documents

    # Limit for iteration:
    python manage.py ingest_documents \
        --include ../data/raw/judged_204.txt --limit 500

Reads doc_id_index.json from data/raw/ (relative to repo root).
Embedding is a separate command — see embed_documents.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from documents.models import Document
from documents.parsing import parse_document_file


class Command(BaseCommand):
    help = "Ingest EDRM Enron v2 base emails from data/raw/ into the Document model."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--data-root",
            default=None,
            help="Corpus root directory (default: <repo_root>/data/raw)",
        )
        parser.add_argument(
            "--index",
            default=None,
            help="Path to doc_id_index.json (default: <data-root>/doc_id_index.json)",
        )
        parser.add_argument(
            "--include",
            default=None,
            help="Path to a file listing doc-ids to include (e.g. judged_204.txt)",
        )
        parser.add_argument(
            "--custodians",
            nargs="+",
            default=None,
            help="Custodians to include as haystack (e.g. dasovich-j germany-c beck-s)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap on docs to process this run (for iteration).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Rows per bulk_create batch (default: 500).",
        )

    # ------------------------- Path resolution -------------------------

    def _resolve_paths(self, opts: dict) -> tuple[Path, Path]:
        repo_root = Path(settings.BASE_DIR).parent
        data_root = Path(opts["data_root"]) if opts["data_root"] else (repo_root / "data" / "raw")
        index_path = Path(opts["index"]) if opts["index"] else (data_root / "doc_id_index.json")
        if not data_root.exists():
            raise CommandError(f"Data root not found: {data_root}")
        if not index_path.exists():
            raise CommandError(f"Index not found: {index_path}")
        return data_root, index_path

    # ------------------------- Selection -------------------------

    def _select(
        self,
        index: dict[str, str],
        include_file: str | None,
        custodians: list[str] | None,
    ) -> list[tuple[str, str]]:
        """Return (doc_id, relative_path) tuples to process this run."""
        if include_file is None and not custodians:
            return list(index.items())

        selected: dict[str, str] = {}

        if include_file:
            for did in Path(include_file).read_text(encoding="utf-8").splitlines():
                did = did.strip()
                if did and did in index:
                    selected[did] = index[did]

        if custodians:
            markers = [f"edrm-enron-v2_{c}_xml" for c in custodians]
            for did, path in index.items():
                if any(m in path for m in markers):
                    selected[did] = path

        return list(selected.items())

    # ------------------------- Main -------------------------

    def handle(self, *args, **opts) -> None:
        t_start = time.time()

        data_root, index_path = self._resolve_paths(opts)
        self.stdout.write(f"Data root: {data_root}")
        self.stdout.write(f"Index:     {index_path}")

        index: dict[str, str] = json.loads(index_path.read_text(encoding="utf-8"))
        self.stdout.write(f"Loaded index: {len(index):,} base emails")

        targets = self._select(index, opts["include"], opts["custodians"])
        if opts["limit"]:
            targets = targets[: opts["limit"]]
        self.stdout.write(f"Selected for this run: {len(targets):,} doc-ids\n")

        n_ok = n_binary = n_decode = n_read = n_unexpected = 0
        batch: list[Document] = []

        for i, (doc_id, rel_path) in enumerate(targets, 1):
            abs_path = data_root / rel_path
            try:
                raw = abs_path.read_bytes()
            except OSError:
                n_read += 1
                continue

            try:
                parsed = parse_document_file(raw, doc_id, str(abs_path))
            except Exception as e:
                n_unexpected += 1
                self.stderr.write(f"  UNEXPECTED on {doc_id}: {e}")
                continue

            if "__skip__" in parsed:
                reason = parsed["__skip__"]
                if reason == "binary_corrupt": n_binary += 1
                elif reason == "decode_error": n_decode += 1
                continue

            batch.append(Document(**parsed))
            n_ok += 1

            if len(batch) >= opts["batch_size"]:
                Document.objects.bulk_create(batch, ignore_conflicts=True)
                batch.clear()

            if i % 1000 == 0:
                self.stdout.write(f"  ...processed {i:,} / {len(targets):,}")

        if batch:
            Document.objects.bulk_create(batch, ignore_conflicts=True)

        elapsed = time.time() - t_start
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Ingest complete in {elapsed:.1f}s"))
        self.stdout.write(f"  Documents ingested (this run): {n_ok:,}")
        self.stdout.write(f"  Binary-corrupt skipped:        {n_binary:,}")
        self.stdout.write(f"  Decode errors:                 {n_decode:,}")
        self.stdout.write(f"  Read errors:                   {n_read:,}")
        self.stdout.write(f"  Unexpected errors:             {n_unexpected:,}")
        self.stdout.write(
            f"  Total in DB now: {Document.objects.count():,}"
        )