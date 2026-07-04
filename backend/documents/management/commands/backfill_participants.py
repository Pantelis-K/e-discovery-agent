"""
One-time management command: correct participant splitting and populate the resolved
display fields on EXISTING Document rows, from each row's raw_headers.

Why this exists (spec §5, identity-resolution work):
The original `split_participants` mis-split ~1,580 documents' To:/Cc: (case-sensitive
`</O=` marker; the "Last, First <addr>" comma trap; bare-comma merges beside an X.500
unit). This command re-derives To/From/Cc from the pristine `raw_headers` (populated
100%) using the corrected `documents.participants.resolve_field`, and writes:
  * to_addrs / cc_addrs  -> corrected raw unit strings (JSON array)
  * from_display         -> one resolved unit  (JSON object, or null)
  * to_display / cc_display -> resolved units  (JSON array)
from_addr is left untouched (raw From is already a clean single value).

It is a PURE DB PASS: no corpus files are read, no embeddings are touched. Idempotent
(safe to re-run) and resumable-by-nature (each row is recomputed from raw_headers).

    python manage.py backfill_participants --dry-run   # counts only, no writes
    python manage.py backfill_participants              # apply

NOTE (serialisation): to_addrs/cc_addrs/*_display are TextField, and read.py reads them
back with json.loads, so this command WRITES json.dumps strings. raw_headers may have
been stored as JSON or as a Python repr (parse_document_file handed Django a dict for a
TextField); we read it defensively (json -> ast.literal_eval). Task 7 fixes the parser
to emit JSON natively so fresh clones don't need this command.
"""

from __future__ import annotations

import ast
import json
import time

from django.core.management.base import BaseCommand

from documents.models import Document
from documents.participants import resolve_field, resolve_unit


def _load_headers(value) -> dict:
    """Tolerantly parse a stored raw_headers value into a dict (JSON or Python repr)."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump(value) -> str | None:
    """JSON-encode a list/object for a TextField; None stays None."""
    return None if value in (None, [], {}) else json.dumps(value, ensure_ascii=False)


class Command(BaseCommand):
    help = "Re-resolve To/From/Cc from raw_headers; correct splits + fill display fields."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Compute and report counts without writing any rows.",
        )
        parser.add_argument(
            "--batch-size", type=int, default=1000,
            help="Rows per bulk_update batch (default: 1000).",
        )

    def handle(self, *args, **opts) -> None:
        t_start = time.time()
        dry_run: bool = opts["dry_run"]
        batch_size: int = opts["batch_size"]

        total = Document.objects.count()
        self.stdout.write(f"Documents to process: {total:,}"
                          + ("  (DRY RUN — no writes)" if dry_run else ""))

        n_seen = n_updated = n_no_headers = 0
        n_to_fixed = n_cc_fixed = 0          # rows whose split actually changed
        batch: list[Document] = []
        fields = ["to_addrs", "cc_addrs", "from_display", "to_display", "cc_display"]

        qs = Document.objects.all().only(
            "doc_id", "to_addrs", "cc_addrs", "raw_headers"
        ).iterator(chunk_size=2000)

        for doc in qs:
            n_seen += 1
            headers = _load_headers(doc.raw_headers)
            if not headers:
                n_no_headers += 1

            # From: is a SINGLE participant per header; resolve as one unit so
            # bare "Last, First" values are not comma-split (that lost the given
            # name in the initial backfill — 6,165 rows corrupted, verified).
            from_raw = (headers.get("From") or "").strip()
            from_unit = resolve_unit(from_raw) if from_raw else None
            to_units = resolve_field(headers.get("To"))
            cc_units = resolve_field(headers.get("Cc"))

            new_to_addrs = _dump([u["raw"] for u in to_units]) if to_units else None
            new_cc_addrs = _dump([u["raw"] for u in cc_units]) if cc_units else None

            if new_to_addrs != doc.to_addrs:
                n_to_fixed += 1
            if new_cc_addrs != doc.cc_addrs:
                n_cc_fixed += 1

            doc.to_addrs = new_to_addrs
            doc.cc_addrs = new_cc_addrs
            doc.from_display = _dump(from_unit) if from_unit else None
            doc.to_display = _dump(to_units) if to_units else None
            doc.cc_display = _dump(cc_units) if cc_units else None

            batch.append(doc)
            if len(batch) >= batch_size:
                if not dry_run:
                    Document.objects.bulk_update(batch, fields)
                n_updated += len(batch)
                batch.clear()

            if n_seen % 20000 == 0:
                self.stdout.write(f"  ...processed {n_seen:,} / {total:,}")

        if batch:
            if not dry_run:
                Document.objects.bulk_update(batch, fields)
            n_updated += len(batch)
            batch.clear()

        elapsed = time.time() - t_start
        self.stdout.write("")
        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(f"Backfill complete in {elapsed:.1f}s"))
        self.stdout.write(f"  Rows processed:              {n_seen:,}")
        self.stdout.write(f"  {verb} rows:                 {n_updated:,}")
        self.stdout.write(f"  to_addrs re-split (changed): {n_to_fixed:,}")
        self.stdout.write(f"  cc_addrs re-split (changed): {n_cc_fixed:,}")
        self.stdout.write(f"  Rows with no raw_headers:    {n_no_headers:,}")