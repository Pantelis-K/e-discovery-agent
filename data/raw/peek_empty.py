import sqlite3
import json
from pathlib import Path

conn = sqlite3.connect("state.db")
index = json.loads(Path("doc_id_index.json").read_text(encoding="utf-8"))

# Grab three zero-body docs that are judged RELEVANT — most diagnostic case
# (if parser is dropping real content, this is where we'd feel it most)
judged = {}
with open("qrels.t10legallearn", encoding="utf-8") as f:
    for line in f:
        parts = line.split()
        if len(parts) != 3 or not parts[0].startswith("204:"):
            continue
        rel = int(parts[2])
        if rel not in (0, 1):
            continue
        judged[parts[0].split(":", 1)[1]] = rel

rel_zero_ids = []
rows = conn.execute("SELECT doc_id FROM documents WHERE body IS NULL OR body = ''").fetchall()
for (d,) in rows:
    if judged.get(d) == 1:
        rel_zero_ids.append(d)
    if len(rel_zero_ids) == 3:
        break

print(f"Sampling {len(rel_zero_ids)} zero-body RELEVANT docs from judged pool\n")

for d in rel_zero_ids:
    path = index[d]
    print("=" * 72)
    print(f"doc_id: {d}")
    print(f"path:   {path}")
    print(f"--- raw file contents ---")
    print(Path(path).read_text(encoding="utf-8", errors="replace"))
    print()