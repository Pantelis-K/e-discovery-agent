"""
search_documents tool (spec §3).

Chroma similarity search over email chunks + SQLite-backed review-state and metadata
filtering. Returns a list of up to 20 unique documents, most-similar first.

FLOW
1. Encode the query with `sentence-transformers/all-MiniLM-L6-v2` (matches
   `embed_documents` — MUST agree or the similarity space is nonsense).
2. Chroma `collection.query` for the top N chunks (N > 20 so we can dedup + filter and
   still return 20 hits). Chunk-level filters go in the Chroma `where` clause:
   `custodian` and `date_range` map cleanly to chunk metadata.
3. Group chunks by doc_id, keep the best-scoring chunk per doc as the snippet.
4. Review-state filter (§3): exclude docs already touched in ANY run — any doc_id
   with a Decision row (proposed OR committed, any run_id) is out. This is what
   stops the agent re-deciding the same handful of documents across separate
   "Bulk approve" batches, as well as within a single batch via a broadened query.
5. Sender-domain filter (post-query): the Chroma `sender` metadata was written by the
   pre-resolver `extract_sender_display` (Task 7 in §5), so it's a display hint, not
   authoritative. Apply the filter against SQLite `Document.from_display[i].domain`
   instead — the resolver-derived source of truth.
6. Attach resolved sender + date from SQL; return top 20.

SCORE
Chroma returns cosine distances in [0, 2]. Return similarity = 1 - distance/2 in
[0, 1] rounded to 4dp. Higher = more relevant. Match the agent's mental model, not
Chroma's internal representation.

MODEL / CLIENT LIFECYCLE
Model + Chroma client are process-wide lazy singletons — first call pays the ~1-2s
cold-load, subsequent calls are millisecond-cheap. Deferred imports so pulling in
`agent.tools` (which imports this module) does NOT force torch/chromadb at import
time — that would break `manage.py migrate` and any test that touches the tools
package without needing search.

ERRORS
`{"error": str}` on Chroma failure or empty query — same shape as the other tools so
the loop can hand the LLM a tool_result it can course-correct on. Empty results are
NOT an error (the LLM should try a different query or `finish_batch`).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings

from agent.models import Decision
from documents.models import Document

logger = logging.getLogger(__name__)

# MUST match embed_documents.py. Sanity: if this drifts, retrieval silently degrades.
CHROMA_COLLECTION = "email_chunks"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Over-fetch so the review-state + sender-domain + dedup passes still leave 20 hits.
# Empirically, chunk-per-doc ratio is ~1.6 on this corpus; 100 chunks -> ~60 unique
# docs before filtering, which comfortably covers 20 after even aggressive filtering.
CHROMA_QUERY_N = 100
RESULT_CAP = 20

# Snippet length for the reasoning stream — long enough to be diagnostic, short
# enough that a batch of 20 hits fits in a reasoning-stream card without a scroll.
SNIPPET_CHARS = 300

_model = None
_collection = None


def _get_model():
    """Lazy singleton for the ST embedder. First call cold-loads (~1-2s)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model


def _get_collection():
    """Lazy singleton for the Chroma collection handle."""
    global _collection
    if _collection is None:
        import chromadb
        repo_root = Path(settings.BASE_DIR).parent
        chroma_dir = repo_root / "data" / "chroma"
        client = chromadb.PersistentClient(path=str(chroma_dir))
        _collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _build_where(filters: dict) -> dict:
    """Translate the tool's filter dict into a Chroma `where` clause.

    Only filters that map cleanly to chunk metadata are included here; sender_domain
    is applied post-query in Python (see module docstring). Returns `{}` when no
    conditions apply — the caller passes `where=None` in that case, because Chroma
    rejects an empty dict.
    """
    conditions: list[dict] = []

    custodian = filters.get("custodian")
    if custodian:
        conditions.append({"custodian": {"$eq": custodian}})

    date_range = filters.get("date_range")
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        if start:
            conditions.append({"date": {"$gte": str(start)}})
        if end:
            conditions.append({"date": {"$lte": str(end)}})

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _passes_sender_domain(from_display_raw: str | None, wanted_domain: str) -> bool:
    """Post-Chroma filter against the resolver's `domain` (SQL, authoritative), not
    the Chroma `sender` metadata (pre-resolver, display hint only — Task 7 in §5)."""
    if not from_display_raw:
        return False
    try:
        unit = json.loads(from_display_raw)
    except (ValueError, TypeError):
        return False
    domain = (unit.get("domain") or "").lower()
    return wanted_domain in domain if domain else False


def _snippet(text: str) -> str:
    """Compact whitespace and truncate for the reasoning stream."""
    text = " ".join((text or "").split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS] + "…"


def _sender_label(from_display_raw: str | None, from_addr: str | None) -> str | None:
    """Prefer the resolver's canonical display; fall back to raw From: for docs
    ingested before Task 7, and null if neither is available (§3 says sender may
    be null; the UI must render around it)."""
    if from_display_raw:
        try:
            unit = json.loads(from_display_raw)
        except (ValueError, TypeError):
            unit = None
        if unit and unit.get("display"):
            return unit["display"]
    return from_addr or None


def search_documents(
    query: str,
    filters: dict | None = None,
    run_id: str | None = None,
) -> list[dict] | dict:
    """Semantic search over the corpus. Returns up to 20 unique docs ranked by
    similarity to `query` and excluding docs already touched in this run.

    Return shape matches spec §3: `list[SearchHit]` on the happy path (possibly
    empty), or `{"error": str}` on failure. Empty result is valid — the LLM should
    vary the query or `finish_batch`.
    """
    filters = filters or {}
    if not query or not query.strip():
        return {"error": "search: empty query"}

    try:
        model = _get_model()
        collection = _get_collection()
        embedding = model.encode([query], show_progress_bar=False)[0].tolist()
        where = _build_where(filters)
        result = collection.query(
            query_embeddings=[embedding],
            n_results=CHROMA_QUERY_N,
            where=where or None,
            include=["documents", "distances", "metadatas"],
        )
    except Exception as e:
        logger.exception("search: Chroma query failed")
        return {"error": f"search: {type(e).__name__} - {e}"}

    ids_2d = result.get("ids") or [[]]
    docs_2d = result.get("documents") or [[]]
    dists_2d = result.get("distances") or [[]]
    metas_2d = result.get("metadatas") or [[]]
    if not ids_2d or not ids_2d[0]:
        return []

    # Dedup: group chunks by doc_id, keep the best-scoring (lowest-distance) chunk.
    # Chroma metadata carries doc_id; fall back to parsing the "doc_id::N" chunk id
    # if a metadata write was ever skipped (defensive; shouldn't happen).
    best: dict[str, tuple[float, str]] = {}
    for chunk_id, text, distance, meta in zip(
        ids_2d[0], docs_2d[0], dists_2d[0], metas_2d[0]
    ):
        doc_id = (meta or {}).get("doc_id") or chunk_id.split("::", 1)[0]
        if doc_id not in best or distance < best[doc_id][0]:
            best[doc_id] = (distance, text)

    if not best:
        return []

    # Review-state filter (§3): exclude docs with ANY Decision, from this run or any
    # earlier one. Each "Bulk approve" starts a fresh run_id, so scoping this to the
    # current run alone let the agent re-surface and re-decide the same top-scoring
    # handful of documents batch after batch instead of making forward progress
    # through the corpus. Covers both "already committed by an earlier batch" and
    # "proposed but not yet committed" — both live in this table, committed=0 or 1.
    if run_id:
        touched = set(
            Decision.objects
            .filter(doc_id_id__in=list(best.keys()))
            .values_list("doc_id_id", flat=True)
        )
        for doc_id in list(best.keys()):
            if doc_id in touched:
                best.pop(doc_id)

    if not best:
        return []

    # SQL join for resolved sender / date and the sender_domain post-filter.
    docs = {
        d.doc_id: d
        for d in Document.objects.filter(doc_id__in=list(best.keys())).only(
            "doc_id", "from_addr", "from_display", "date"
        )
    }

    sender_domain = (filters.get("sender_domain") or "").strip().lower()

    hits: list[dict] = []
    for doc_id, (distance, chunk_text) in best.items():
        doc = docs.get(doc_id)
        if doc is None:
            # Race: a Document row disappeared between Chroma and SQL. Extremely
            # unlikely (documents are immutable-ish); skip rather than surface.
            continue
        if sender_domain and not _passes_sender_domain(doc.from_display, sender_domain):
            continue
        hits.append({
            "doc_id":  doc_id,
            # cosine distance in [0, 2] -> similarity in [0, 1], higher = more similar
            "score":   round(max(0.0, 1.0 - (distance / 2.0)), 4),
            "snippet": _snippet(chunk_text),
            "sender":  _sender_label(doc.from_display, doc.from_addr),
            "date":    doc.date.isoformat() if doc.date else None,
        })

    hits.sort(key=lambda h: -h["score"])
    return hits[:RESULT_CAP]
