"""
Django management command: chunk & embed Document bodies into Chroma.

Idempotent — skips chunks already in Chroma by chunk_id (doc_id::N).
Reads only documents with a non-empty body; zero-body docs (calendar items,
Notes housekeeping records) are correctly excluded from retrieval.

Run via manage.py from backend/:

    # Embed everything currently ingested:
    python manage.py embed_documents

    # Iteration:
    python manage.py embed_documents --limit 100

    # GPU (falls back to CPU if driver misbehaves):
    python manage.py embed_documents --device cuda

Chroma persistent dir defaults to <repo_root>/data/chroma/ — colocated with the
raw corpus, matches spec §5 intent.
"""

from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.models import Document
from documents.parsing import chunk_text, extract_sender_display


CHROMA_COLLECTION = "email_chunks"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Command(BaseCommand):
    help = "Chunk Document bodies and embed into Chroma."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--chroma-dir",
            default=None,
            help="Chroma persistent directory (default: <repo_root>/data/chroma)",
        )
        parser.add_argument(
            "--device",
            default="cpu",
            help="Embedding device: cpu or cuda (default: cpu).",
        )
        parser.add_argument(
            "--embed-batch",
            type=int,
            default=256,
            help="Chunks per Chroma write batch (default: 256).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap on docs to embed this run (for iteration).",
        )

    def handle(self, *args, **opts) -> None:
        t_start = time.time()

        repo_root = Path(settings.BASE_DIR).parent
        chroma_dir = Path(opts["chroma_dir"]) if opts["chroma_dir"] else (repo_root / "data" / "chroma")
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self.stdout.write(f"Chroma dir: {chroma_dir}")

        # Deferred imports so ingest_documents doesn't pull heavy deps
        self.stdout.write("Loading embedding model (first run downloads ~90MB)...")
        from sentence_transformers import SentenceTransformer
        import chromadb

        model = SentenceTransformer(EMBEDDING_MODEL, device=opts["device"])
        self.stdout.write(f"Model loaded (device={opts['device']})")

        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

        try:
            existing_chunks = set(collection.get(include=[])["ids"])
            self.stdout.write(f"Chroma already holds {len(existing_chunks):,} chunk ids")
        except Exception as e:
            self.stdout.write(f"Chroma read warning: {e}")
            existing_chunks = set()

        # Iterate docs with non-empty bodies via the ORM
        qs = Document.objects.exclude(body__isnull=True).exclude(body="").only(
            "doc_id", "from_addr", "custodian", "date", "body"
        )
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        buf_ids: list[str] = []
        buf_texts: list[str] = []
        buf_meta: list[dict] = []

        n_chunks = 0
        n_docs_embedded = 0
        embed_batch_size = opts["embed_batch"]

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

        # Use iterator() for memory efficiency on the overnight run
        for doc in qs.iterator(chunk_size=1000):
            chunks = chunk_text(doc.body)
            if not chunks:
                continue

            any_new = False
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc.doc_id}::{i}"
                if chunk_id in existing_chunks:
                    continue
                any_new = True
                buf_ids.append(chunk_id)
                buf_texts.append(chunk)
                buf_meta.append({
                    "doc_id":      doc.doc_id,
                    "chunk_index": i,
                    "sender":      extract_sender_display(doc.from_addr) or "",
                    "custodian":   doc.custodian or "",
                    "date":        doc.date.isoformat() if doc.date else "",
                })
                if len(buf_ids) >= embed_batch_size:
                    flush()

            if any_new:
                n_docs_embedded += 1
                if n_docs_embedded % 500 == 0:
                    elapsed = time.time() - t_start
                    rate = n_docs_embedded / elapsed if elapsed else 0
                    self.stdout.write(
                        f"  ...embedded {n_docs_embedded:,} docs "
                        f"({n_chunks:,} chunks, {rate:.1f} docs/s)"
                    )

        flush()

        elapsed = time.time() - t_start
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Embedding complete in {elapsed:.1f}s"))
        self.stdout.write(f"  Docs embedded this run:   {n_docs_embedded:,}")
        self.stdout.write(f"  Chunks written to Chroma: {n_chunks:,}")
        self.stdout.write(f"  Total chunks in Chroma:   {collection.count():,}")