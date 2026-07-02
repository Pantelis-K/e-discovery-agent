import sqlite3, json, random

conn = sqlite3.connect("state.db")
random.seed(42)  # reproducible

rows = conn.execute("SELECT doc_id, subject, from_addr, to_addrs, date, body, custodian FROM documents").fetchall()
sample = random.sample(rows, 3)

for doc_id, subject, from_addr, to_addrs, date, body, custodian in sample:
    print("=" * 70)
    print(f"doc_id:    {doc_id}")
    print(f"custodian: {custodian}")
    print(f"subject:   {subject!r}")
    print(f"from:      {from_addr!r}")
    print(f"to:        {to_addrs!r}")
    print(f"date:      {date}")
    print(f"body length: {len(body)} chars")
    print(f"body preview (first 400 chars):")
    print(body[:400])
    print(f"\nbody tail (last 200 chars):")
    print(body[-200:])
    print(f"\nnul bytes in body: {body.count(chr(0))}")
    print()