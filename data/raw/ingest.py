#!/usr/bin/env python3
"""
ingest.py — EDRM Enron v2 base-email loader.

Populates state.db (SQLite) and chroma/ (Chroma vector index) from base-email
.txt files under the corpus directories. Read spec §5 and §6 before editing.

Run from data/raw/. All defaults assume that CWD.

Usage:
    # Dev subset (Day 1 morning):
    python ingest.py --include judged_204.txt \
        --custodians dasovich-j germany-c beck-s

    # Full corpus (overnight — no filter flags):
    python ingest.py

    # SQLite only, skip Chroma (fast iteration on parsing changes):
    python ingest.py --include judged_204.txt --no-embed
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

# ------------------------- Config -------------------------

DEFAULT_INDEX = "doc_id_index.json"
DEFAULT_DB = "state.db"
DEFAULT_CHROMA_DIR = "chroma"
CHROMA_COLLECTION = "email_chunks"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Chunking approximation: 500 tokens ~ 2000 chars, 50 overlap ~ 200 chars.
# MiniLM truncates at 256 tokens internally — this is fine and standard.
CHUNK_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200

# §5: reject files whose NUL byte fraction exceeds this threshold.
# ~1.7% of the corpus is binary-corrupt (OLE2 bytes leaked into .txt).
NUL_RATIO_THRESHOLD = 0.01

# ZL boilerplate footer boundary (line of asterisks)
ZL_BOUNDARY_RE = re.compile(r"^\*{5,}\s*$")

# Marker for Exchange X.500 addressing — decides participant-split strategy
X500_MARKER = "</O="


# ------------------------- Parsing helpers -------------------------


def is_binary_corrupt(raw: bytes) -> bool:
    """Detect NUL-heavy leaked binary per §5."""
    if not raw:
        return False
    return (raw.count(b"\x00") / len(raw)) > NUL_RATIO_THRESHOLD


def decode_text(raw: bytes) -> str | None:
    """UTF-8 first, latin-1 fallback. None if nothing works."""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


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
    joined onto the prior field. Unknown headers preserved.
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
        # Restore the '>' consumed by the split, on parts that contain X.500
        parts = [
            p + ">" if X500_MARKER in p and not p.endswith(">") else p
            for p in parts
        ]
        return [p.strip() for p in parts if p.strip()]
    return [p.strip() for p in value.split(",") if p.strip()]


def parse_date(value: str) -> str | None:
    """RFC 2822 -> ISO string. None if unparseable."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.isoformat() if dt else None
    except (TypeError, ValueError):
        return None


def extract_sender_display(from_raw: str | None) -> str | None:
    """For Chroma metadata: best available sender label."""
    if not from_raw:
        return None
    if "<" in from_raw:
        display = from_raw.split("<", 1)[0].strip().strip('"').strip()
        if display:
            return display
    return from_raw.strip()


def custodian_from_path(path_str: str) -> str:
    """
    Extract custodian name from the .zip directory in the path.
    Path shape: edrm-enron-v2_<custodian>_xml[_NofM].zip/text_NNN/<docid>.txt
    """
    # Normalise separators
    parts = re.split(r"[\\/]+", path_str)
    for seg in parts:
        if seg.startswith("edrm-enron-v2_") and seg.endswith(".zip"):
            stem = seg[len("edrm-enron-v2_"):-len(".zip")]
            return re.sub(r"_xml(_\d+of\d+)?$", "", stem)
    return "unknown"


# ------------------------- SQLite -------------------------

DDL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS documents (
    doc_id           TEXT PRIMARY KEY,
    x_sdoc           TEXT,
    x_zlid           TEXT,
    message_id       TEXT,
    thread_id        TEXT,
    subject          TEXT,
    from_addr        TEXT,
    to_addrs         TEXT,
    cc_addrs         TEXT,
    bcc_addrs        TEXT,
    date             TEXT,
    body             TEXT,
    custodian        TEXT,
    attachment_refs  TEXT,
    raw_headers      TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_date       ON documents(date);
CREATE INDEX IF NOT EXISTS idx_documents_from       ON documents(from_addr);
CREATE INDEX IF NOT EXISTS idx_documents_custodian  ON documents(custodian);
CREATE INDEX IF NOT EXISTS idx_documents_thread     ON documents(thread_id);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    conn.commit()
    return conn


def existing_doc_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT doc_id FROM documents")}


def insert_document(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO documents
        (doc_id, x_sdoc, x_zlid, message_id, thread_id, subject,
         from_addr, to_addrs, cc_addrs, bcc_addrs, date, body,
         custodian, attachment_refs, raw_headers)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["doc_id"], row["x_sdoc"], row["x_zlid"],
            row["message_id"], row["thread_id"], row["subject"],
            row["from_addr"], row["to_addrs"], row["cc_addrs"],
            row["bcc_addrs"], row["date"], row["body"],
            row["custodian"], row["attachment_refs"], row["raw_headers"],
        ),
    )


# ------------------------- Chunker -------------------------


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
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


# ------------------------- Per-file processing -------------------------


def process_one_file(doc_id: str, path: Path) -> dict:
    """Read + parse one file. Returns row dict OR {'__skip__': reason}."""
    try:
        raw = path.read_bytes()
    except OSError:
        return {"__skip__": "read_error"}

    if is_binary_corrupt(raw):
        return {"__skip__": "binary_corrupt"}

    text = decode_text(raw)
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
        "to_addrs":        json.dumps(split_participants(to_raw)) if to_raw else None,
        "cc_addrs":        json.dumps(split_participants(cc_raw)) if cc_raw else None,
        "bcc_addrs":       None,  # never populated (Bcc absent from corpus)
        "date":            parse_date(headers.get("Date") or ""),
        "body":            body,
        "custodian":       custodian_from_path(str(path)),
        "attachment_refs": json.dumps(attachment_refs) if attachment_refs else None,
        "raw_headers":     json.dumps(headers),
    }


# ------------------------- Selection -------------------------


def select_doc_ids(
    index: dict[str, str],
    include_file: str | None,
    custodians: list[str] | None,
) -> list[tuple[str, str]]:
    """
    Return (doc_id, path) tuples to ingest this run.
    - include_file adds those doc_ids (verbatim).
    - custodians adds every doc from those custodian directories.
    - Neither: full corpus.
    """
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


def run(args: argparse.Namespace) -> int:
    t_start = time.time()

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"ERROR: index not found at {index_path}", file=sys.stderr)
        return 2
    index: dict[str, str] = json.loads(index_path.read_text(encoding="utf-8"))
    print(f"Loaded index: {len(index):,} base emails")

    targets = select_doc_ids(index, args.include, args.custodians)
    print(f"Selected for this run: {len(targets):,} doc-ids")

    conn = init_db(args.db)
    already = existing_doc_ids(conn)
    print(f"Already in DB (will skip): {len(already):,}")

    to_process = [(d, p) for d, p in targets if d not in already]
    print(f"To ingest this run: {len(to_process):,}\n")

    n_ok = n_binary = n_decode = n_read = n_unexpected = 0

    for i, (doc_id, path_str) in enumerate(to_process, 1):
        try:
            row = process_one_file(doc_id, Path(path_str))
            if "__skip__" in row:
                reason = row["__skip__"]
                if reason == "binary_corrupt": n_binary += 1
                elif reason == "decode_error": n_decode += 1
                elif reason == "read_error":   n_read += 1
                continue
            insert_document(conn, row)
            n_ok += 1
        except Exception as e:
            n_unexpected += 1
            print(f"  UNEXPECTED on {doc_id}: {e}", file=sys.stderr)

        if i % 1000 == 0:
            conn.commit()
            print(f"  ...processed {i:,} / {len(to_process):,}")

    conn.commit()
    t_sqlite = time.time() - t_start
    print(f"\nSQLite ingest complete in {t_sqlite:.1f}s")
    print(f"  Documents ingested:      {n_ok:,}")
    print(f"  Binary-corrupt skipped:  {n_binary:,}")
    print(f"  Decode errors:           {n_decode:,}")
    print(f"  Read errors:             {n_read:,}")
    print(f"  Unexpected errors:       {n_unexpected:,}")

    if args.no_embed:
        print("\n--no-embed set — skipping Chroma embedding.")
        conn.close()
        return 0

    # ---------------- Embedding ----------------

    print("\nLoading embedding model (first run downloads ~90MB)...")
    from sentence_transformers import SentenceTransformer
    import chromadb

    model = SentenceTransformer(EMBEDDING_MODEL, device=args.device)
    print(f"Model loaded (device={args.device})")

    chroma_client = chromadb.PersistentClient(path=args.chroma_dir)
    collection = chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
    )

    try:
        existing_chunks = set(collection.get(include=[])["ids"])
        print(f"Chroma already holds {len(existing_chunks):,} chunk ids")
    except Exception as e:
        print(f"Chroma read warning: {e}")
        existing_chunks = set()

    cur = conn.execute(
        "SELECT doc_id, subject, from_addr, custodian, date, body FROM documents "
        "WHERE body IS NOT NULL AND body != ''"
    )

    buf_ids:   list[str] = []
    buf_texts: list[str] = []
    buf_meta:  list[dict] = []

    n_chunks = 0
    n_docs_embedded = 0
    t_embed_start = time.time()

    def flush() -> None:
        nonlocal n_chunks
        if not buf_texts:
            return
        embeddings = model.encode(buf_texts, batch_size=64, show_progress_bar=False)
        collection.add(
            ids=buf_ids,
            embeddings=[e.tolist() for e in embeddings],
            documents=buf_texts,
            metadatas=buf_meta,
        )
        n_chunks += len(buf_ids)
        buf_ids.clear()
        buf_texts.clear()
        buf_meta.clear()

    for doc_id, subject, from_addr, custodian, date_iso, body in cur:
        chunks = chunk_text(body, CHUNK_CHARS, CHUNK_OVERLAP_CHARS)
        if not chunks:
            continue
        any_new = False
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}::{i}"
            if chunk_id in existing_chunks:
                continue
            any_new = True
            buf_ids.append(chunk_id)
            buf_texts.append(chunk)
            buf_meta.append({
                "doc_id":      doc_id,
                "chunk_index": i,
                "sender":      extract_sender_display(from_addr) or "",
                "custodian":   custodian or "",
                "date":        date_iso or "",
            })
            if len(buf_ids) >= args.embed_batch:
                flush()
        if any_new:
            n_docs_embedded += 1
            if n_docs_embedded % 500 == 0:
                el = time.time() - t_embed_start
                rate = n_docs_embedded / el if el else 0
                print(f"  ...embedded {n_docs_embedded:,} docs "
                      f"({n_chunks:,} chunks, {rate:.1f} docs/s)")
    flush()

    t_embed = time.time() - t_embed_start
    print(f"\nEmbedding complete in {t_embed:.1f}s")
    print(f"  Docs embedded this run:   {n_docs_embedded:,}")
    print(f"  Chunks written to Chroma: {n_chunks:,}")

    conn.close()
    print(f"\nTotal wall time: {time.time() - t_start:.1f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EDRM Enron v2 base-email loader.")
    p.add_argument("--index",       default=DEFAULT_INDEX,
                   help=f"Path to doc_id_index.json (default: {DEFAULT_INDEX})")
    p.add_argument("--db",          default=DEFAULT_DB,
                   help=f"SQLite path (default: {DEFAULT_DB})")
    p.add_argument("--chroma-dir",  default=DEFAULT_CHROMA_DIR,
                   help=f"Chroma dir (default: {DEFAULT_CHROMA_DIR})")
    p.add_argument("--include",     default=None,
                   help="File listing doc-ids to include (e.g. judged_204.txt)")
    p.add_argument("--custodians",  nargs="+", default=None,
                   help="Extra custodians as haystack (e.g. dasovich-j germany-c beck-s)")
    p.add_argument("--no-embed",    action="store_true",
                   help="Skip Chroma embedding (SQLite only)")
    p.add_argument("--device",      default="cpu",
                   help="Embedding device: cpu or cuda (default: cpu)")
    p.add_argument("--embed-batch", type=int, default=256,
                   help="Chunks per Chroma write batch (default: 256)")
    return p


if __name__ == "__main__":
    sys.exit(run(build_parser().parse_args()))