"""
Corpus parsing helpers for EDRM Enron v2 base emails.

Pure functions with no Django dependency. Consumed by:
- documents.management.commands.ingest_documents (parsing)
- documents.management.commands.embed_documents  (chunking)
- run_eval.py                                    (body access, if it needs to re-parse)

Read spec §5 before editing. Any change to parsing rules should be reflected there.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

# ------------------------- Constants -------------------------

# §5: reject files whose NUL-byte fraction exceeds this threshold.
# Empirically ~1.7% corpus-wide is binary-corrupt (OLE2 leaked into .txt).
NUL_RATIO_THRESHOLD = 0.01

# ZL boilerplate footer boundary — line of asterisks
ZL_BOUNDARY_RE = re.compile(r"^\*{5,}\s*$")

# Marker for Exchange X.500 addressing — decides participant-split strategy
X500_MARKER = "</O="

# Chunker defaults — 500 tokens with 50 overlap at ~4 chars/token.
CHUNK_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200


# ------------------------- File-level helpers -------------------------


def is_binary_corrupt(raw: bytes) -> bool:
    """Detect NUL-heavy leaked binary per §5."""
    if not raw:
        return False
    return (raw.count(b"\x00") / len(raw)) > NUL_RATIO_THRESHOLD


def decode_text(raw: bytes) -> str | None:
    """UTF-8 first, latin-1 fallback. None if both fail."""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


# ------------------------- Structural parsing -------------------------


def split_header_body(text: str) -> tuple[str, str]:
    """First blank line separates header from the rest of the file."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    idx = text.find("\n\n")
    if idx == -1:
        return text, ""
    return text[:idx], text[idx + 2:]


def strip_zl_footer(rest: str) -> tuple[str, list[dict]]:
    """
    Strip the ZL boilerplate footer bracketed by asterisk lines.
    Return (clean_body, attachment_refs). Attachment refs come from
    'Attachment: <filename> type=<mimetype>' lines AFTER the closing boundary.
    """
    lines = rest.split("\n")
    first_boundary = next(
        (i for i, ln in enumerate(lines) if ZL_BOUNDARY_RE.match(ln)), None
    )
    if first_boundary is None:
        return rest.rstrip(), []

    body = "\n".join(lines[:first_boundary]).rstrip()

    second_boundary = next(
        (i for i in range(first_boundary + 1, len(lines))
         if ZL_BOUNDARY_RE.match(lines[i])), None
    )

    attachment_refs: list[dict] = []
    if second_boundary is not None:
        for line in lines[second_boundary + 1:]:
            line = line.strip()
            if not line.startswith("Attachment:"):
                continue
            m = re.match(r"Attachment:\s*(.+?)\s+type=(.+)$", line)
            if m:
                attachment_refs.append(
                    {"filename": m.group(1).strip(), "mimetype": m.group(2).strip()}
                )
            else:
                attachment_refs.append(
                    {"filename": line[len("Attachment:"):].strip(), "mimetype": None}
                )

    return body, attachment_refs


def parse_header_block(header_text: str) -> dict:
    """
    Parse 'Key: value' lines. Continuation lines (leading whitespace) are
    joined onto the prior field. Unknown headers preserved verbatim.
    """
    fields: dict = {}
    current_key: str | None = None
    for raw_line in header_text.split("\n"):
        if not raw_line.strip():
            continue
        if raw_line[0] in " \t" and current_key:
            fields[current_key] = fields[current_key] + " " + raw_line.strip()
            continue
        if ":" in raw_line:
            key, _, value = raw_line.partition(":")
            current_key = key.strip()
            fields[current_key] = value.strip()
        else:
            current_key = None
    return fields


# ------------------------- Participant handling -------------------------


def split_participants(value: str) -> list[str]:
    """
    Split a To:/Cc:/From: value into individual participants.

    §5 trap: display names contain commas ("Last, First"). If the value
    contains X.500 forms, split on the '>,' boundary between units.
    Otherwise plain comma-split is safe.
    """
    if not value:
        return []
    value = value.strip()
    if X500_MARKER in value:
        parts = re.split(r">\s*,\s*", value)
        parts = [
            p + ">" if X500_MARKER in p and not p.endswith(">") else p
            for p in parts
        ]
        return [p.strip() for p in parts if p.strip()]
    return [p.strip() for p in value.split(",") if p.strip()]


def extract_sender_display(from_raw: str | None) -> str | None:
    """For Chroma metadata: best available sender label from a From: value."""
    if not from_raw:
        return None
    if "<" in from_raw:
        display = from_raw.split("<", 1)[0].strip().strip('"').strip()
        if display:
            return display
    return from_raw.strip()


# ------------------------- Dates -------------------------


def parse_date(value: str) -> datetime | None:
    """RFC 2822 -> datetime. None if unparseable (Django DateTimeField accepts None)."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt else None
    except (TypeError, ValueError):
        return None


# ------------------------- Custodian -------------------------


def custodian_from_path(path_str: str) -> str:
    """
    Extract custodian name from the .zip directory in the path.
    Path shape: .../edrm-enron-v2_<custodian>_xml[_NofM].zip/text_NNN/<docid>.txt
    """
    parts = re.split(r"[\\/]+", path_str)
    for seg in parts:
        if seg.startswith("edrm-enron-v2_") and seg.endswith(".zip"):
            stem = seg[len("edrm-enron-v2_"):-len(".zip")]
            return re.sub(r"_xml(_\d+of\d+)?$", "", stem)
    return "unknown"


# ------------------------- Chunking -------------------------


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Simple sliding-window char-based chunker."""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [
        text[i:i + size]
        for i in range(0, len(text), step)
        if text[i:i + size]
    ]


# ------------------------- Composed pipeline -------------------------

def _json_or_none(value) -> str | None:
    """Serialise a list/dict to a JSON string for a TEXT column (spec §6:
    to_addrs/cc_addrs/attachment_refs/raw_headers are `TEXT -- JSON`). None stays None.
    read.py reads these back with json.loads, so they must be JSON, not Python repr."""
    return None if value in (None, [], {}) else json.dumps(value, ensure_ascii=False)


def parse_document_file(path_bytes: bytes, doc_id: str, path_str: str) -> dict | None:
    """
    Take file bytes + metadata, return a dict ready to populate the Document
    model, or None if the file should be skipped. Skip reasons returned as
    {'__skip__': <reason>} rather than exceptions.

    JSON-shaped fields (to_addrs, cc_addrs, attachment_refs, raw_headers) are returned
    as JSON STRINGS, because the model stores them in TextField columns (spec §6:
    `TEXT -- JSON`) and read.py parses them back with json.loads. `date` stays a
    datetime (the real DateTimeField serialises it). Assigning a raw Python list/dict
    to a TextField str()-reprs it (single quotes) and breaks json.loads downstream —
    that was the prior bug.
    """
    if is_binary_corrupt(path_bytes):
        return {"__skip__": "binary_corrupt"}

    text = decode_text(path_bytes)
    if text is None:
        return {"__skip__": "decode_error"}

    header_text, rest = split_header_body(text)
    body, attachment_refs = strip_zl_footer(rest)
    headers = parse_header_block(header_text)

    to_raw = headers.get("To") or ""
    cc_raw = headers.get("Cc") or ""

    return {
        "doc_id":          doc_id,
        "x_sdoc":          headers.get("X-SDOC") or None,
        "x_zlid":          headers.get("X-ZLID") or None,
        "message_id":      headers.get("Message-ID") or None,
        "thread_id":       doc_id,  # placeholder — find_thread cut per rev-3
        "subject":         headers.get("Subject") or None,
        "from_addr":       headers.get("From") or None,
        "to_addrs":        _json_or_none(split_participants(to_raw)) if to_raw else None,
        "cc_addrs":        _json_or_none(split_participants(cc_raw)) if cc_raw else None,
        "bcc_addrs":       None,  # never populated (Bcc absent from corpus)
        "date":            parse_date(headers.get("Date") or ""),
        "body":            body,
        "custodian":       custodian_from_path(path_str),
        "attachment_refs": _json_or_none(attachment_refs),
        "raw_headers":     _json_or_none(headers),
    }