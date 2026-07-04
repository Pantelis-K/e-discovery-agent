"""
Read-only management command: suggest Exchange CN codes for each lawyer in
agent/lawyers.py, mined from the resolved participant display fields.

Every x500_named unit carries (cn_code, display) after the identity-resolution backfill,
so we can pair CN codes to display names corpus-wide and surface, per lawyer, the CN
codes whose display names match. This SUGGESTS ONLY - it prints candidates for you to
eyeball (surname collisions are real: Tana Jones vs Karen Jones; Cook / Moore / Davis)
and paste the confirmed codes into lawyers.py. It never writes the file or the DB.

    python manage.py suggest_lawyer_cn_codes
    python manage.py suggest_lawyer_cn_codes --min-hits 5   # ignore rare/noisy codes

A candidate is shown when any lawyer display-variant token-matches any display name seen
for that CN code (same token-subset rule the privilege matcher uses).
"""

from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from agent.lawyers import LAWYERS
from documents.models import Document
from documents.participants import token_subset_match


def _units(value, single: bool = False) -> list[dict]:
    """Parse a *_display TEXT field (JSON) into a list of unit dicts, tolerantly."""
    if not value:
        return []
    if isinstance(value, (list, dict)):
        parsed = value
    else:
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
    if single:
        return [parsed] if isinstance(parsed, dict) else []
    return parsed if isinstance(parsed, list) else []


class Command(BaseCommand):
    help = "Suggest CN codes per lawyer from resolved x500_named participants (read-only)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--min-hits", type=int, default=1,
            help="Ignore CN codes seen fewer than this many times (default: 1).",
        )

    def handle(self, *args, **opts) -> None:
        min_hits: int = opts["min_hits"]

        # cn_code -> Counter(display name -> occurrences), across from/to/cc.
        cn_names: dict[str, Counter] = defaultdict(Counter)
        n_units = 0

        qs = Document.objects.only(
            "from_display", "to_display", "cc_display"
        ).iterator(chunk_size=2000)
        for doc in qs:
            units = (
                _units(doc.from_display, single=True)
                + _units(doc.to_display)
                + _units(doc.cc_display)
            )
            for u in units:
                if u.get("kind") == "x500_named" and u.get("cn_code") and u.get("display"):
                    cn_names[u["cn_code"]][u["display"]] += 1
                    n_units += 1

        self.stdout.write(
            f"Scanned resolved participants: {n_units:,} x500_named units, "
            f"{len(cn_names):,} distinct CN codes.\n"
        )

        for lawyer in LAWYERS:
            variants = lawyer.get("display_variants", [])
            existing = lawyer.get("cn_codes", [])

            candidates = []
            for cn, names in cn_names.items():
                if sum(names.values()) < min_hits:
                    continue
                if any(token_subset_match(v, name) for v in variants for name in names):
                    candidates.append((cn, sum(names.values()), names.most_common(3)))
            candidates.sort(key=lambda c: c[1], reverse=True)

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"{lawyer['name']}  (current cn_codes: {existing or '[]'})"
            ))
            if not candidates:
                self.stdout.write("    (no CN candidates found)\n")
                continue
            # More than one distinct surname among candidates => likely collision.
            surnames = {name.split(",")[0].strip().lower()
                        for _, _, top in candidates for name, _ in top}
            if len(surnames) > 1:
                self.stdout.write(self.style.WARNING(
                    "    ! multiple surnames among candidates - check for collisions"
                ))
            for cn, hits, top in candidates:
                names_str = "; ".join(f"{name} ({c})" for name, c in top)
                self.stdout.write(f"    CN={cn:<24} hits={hits:<6} {names_str}")
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(
            "Review candidates, then paste the confirmed CN codes into agent/lawyers.py. "
            "Nothing was written."
        ))