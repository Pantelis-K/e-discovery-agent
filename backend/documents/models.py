"""
Document model — base emails from the EDRM Enron v2 corpus.

Reflects spec §6 exactly. Fields marked nullable are so because §5 documented
corpus realities require it (frequently-missing headers, header-only docs, etc.).
Attachments are not ingested per the revision-3 defer list.

Populated by `manage.py ingest_documents`. Read by everything downstream:
- `manage.py embed_documents` (body → Chroma)
- The agent loop's `read_document` tool
- `run_eval.py` (classification against qrels gold)
- The cockpit UI (rendering)
"""

from __future__ import annotations

from django.db import models


class Document(models.Model):
    """One row per ingested base email. Immutable after ingestion."""

    # ---------- Identity ----------

    doc_id = models.CharField(
        max_length=200,
        primary_key=True,
        help_text="Filename stem = TREC canonical doc-id = qrel join key",
    )
    x_sdoc = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="ZL identifier — reliably present (§5)",
    )
    x_zlid = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="ZL identifier — reliably present (§5)",
    )

    # ---------- Threading (largely absent in this corpus) ----------

    message_id = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Essentially always null — no Message-ID header in this corpus (§5)",
    )
    thread_id = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Placeholder set to doc_id — find_thread cut per revision 3 (§8)",
    )

    # ---------- Participants (frequently null per §5) ----------

    subject = models.TextField(
        null=True,
        blank=True,
        help_text="Present on ~96% of docs (§5)",
    )
    from_addr = models.TextField(
        null=True,
        blank=True,
        help_text=(
            "Raw From value in one of four observed forms: clean SMTP, X.500 DN, "
            "bare display name, or Notes-gateway encoded (IMCEANOTES-…). "
            "Missing on ~17% of docs (§5)."
        ),
    )
    to_addrs = models.JSONField(
        null=True,
        blank=True,
        help_text="List of raw participant strings, split per §5 rules. Null when To: absent.",
    )
    cc_addrs = models.JSONField(
        null=True,
        blank=True,
        help_text="List of raw participant strings. Null when Cc: absent.",
    )
    bcc_addrs = models.JSONField(
        null=True,
        blank=True,
        help_text="Never populated — Bcc absent from corpus. Kept for schema shape (§6).",
    )

    # ---------- Content ----------

    date = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Reliably present in headers but occasionally epoch-0 (1979-12-31 PST) "
            "for synthetic records like Notes housekeeping entries."
        ),
    )
    body = models.TextField(
        null=True,
        blank=True,
        help_text=(
            "ZL boilerplate footer stripped. Empty string on header-only records "
            "(calendar items, delivery receipts, Notes housekeeping). "
            "The embed pipeline filters these out."
        ),
    )

    # ---------- Provenance ----------

    custodian = models.CharField(
        max_length=100,
        help_text=(
            "Custodian directory name (e.g. 'dasovich-j'). Always present. "
            "NB: custodian ≠ sender — this is whose mailbox the doc was collected from."
        ),
    )
    attachment_refs = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "List of {filename, mimetype} from 'Attachment:' lines. "
            "Records that an attachment existed; attachment files themselves are not ingested."
        ),
    )
    raw_headers = models.JSONField(
        help_text="Full parsed header dict, preserved for later re-derivation.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["from_addr"]),
            models.Index(fields=["custodian"]),
            models.Index(fields=["thread_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.doc_id} — {self.subject or '(no subject)'}"