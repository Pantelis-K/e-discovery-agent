"""
read_document tool (spec §3).

Deterministic ORM fetch of a single base-email Document. No LLM in the loop.

Returns a JSON-serialisable dict matching the §3 Document shape. Fields that are
frequently absent in the EDRM corpus (subject / from / to / cc) come back as
null / empty rather than raising — the agent prompt is told to expect this and
must not read a blank `from` as anonymity (spec §3 field-availability reality, §5).

`attachments` is always an empty list in the demo build: attachment documents are
out of scope and base emails only are ingested (spec §3). The field is present for
shape compatibility. (Per-document attachment *metadata* still lives on
Document.attachment_refs if a later UI feature wants it.)
"""

from __future__ import annotations

import json

from documents.models import Document


def _json_list(value) -> list:
    """Parse a TEXT field storing a JSON array; tolerate null / already-a-list /
    a bare unparsed string."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        # Stored as a bare string (e.g. a single unparsed address) — surface as-is
        return [value]
    return parsed if isinstance(parsed, list) else [parsed]


def read_document(doc_id: str) -> dict:
    """Fetch one document by id. Returns a dict, or {"error": ...} if not found.

    The error shape is deliberately the same {"error": str} the dispatch table and
    other tools use, so the loop hands a tool_result the LLM can course-correct on
    (spec §2 failure modes) rather than raising into the streaming generator.
    """
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        return {"error": f"document not found: {doc_id}"}

    return {
        "doc_id": doc.doc_id,
        "subject": doc.subject,                              # often null (~96% present)
        "from": doc.from_addr,                               # often null; SMTP / X.500 DN / bare name
        "to": _json_list(doc.to_addrs),                      # often empty (~66% present)
        "cc": _json_list(doc.cc_addrs),                      # usually empty (~11% present)
        "date": doc.date.isoformat() if doc.date else None,  # always present in practice
        "body": doc.body or "",
        "custodian": doc.custodian,
        "attachments": [],                                   # always [] in demo (spec §3)
    }