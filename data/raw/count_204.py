from pathlib import Path

path = Path("qrels.t10legallearn")
count_all = 0
count_rel = 0
count_nrel = 0
attach_dropped = 0
stratum_hist = {}

with path.open(encoding="utf-8") as f:
    for line in f:
        parts = line.split()
        if len(parts) != 3:
            continue
        key, stratum, rel = parts
        if not key.startswith("204:"):
            continue
        rel_i = int(rel)
        if rel_i not in (0, 1):
            continue
        docid = key.split(":", 1)[1]
        segs = docid.split(".")
        # Base:       3.<num>.<HASH>         -> 3 segments
        # Attachment: 3.<num>.<HASH>.<N>     -> 4+, last is a digit
        if len(segs) >= 4 and segs[-1].isdigit():
            attach_dropped += 1
            continue
        count_all += 1
        stratum_hist[stratum] = stratum_hist.get(stratum, 0) + 1
        if rel_i == 1:
            count_rel += 1
        else:
            count_nrel += 1

print(f"Topic 204 judged base-emails: {count_all}")
print(f"  relevant:     {count_rel}")
print(f"  non-relevant: {count_nrel}")
print(f"Attachment doc-ids dropped: {attach_dropped}")
print(f"Stratum distribution (base emails only): {stratum_hist}")

# Persist for downstream: Task 3 disk-join verify + ingest.py priority list
judged_ids = []
with path.open(encoding="utf-8") as f:
    for line in f:
        parts = line.split()
        if len(parts) != 3: continue
        key, _, rel = parts
        if not key.startswith("204:") or int(rel) not in (0, 1): continue
        docid = key.split(":", 1)[1]
        segs = docid.split(".")
        if len(segs) >= 4 and segs[-1].isdigit(): continue
        judged_ids.append(docid)
Path("judged_204.txt").write_text("\n".join(judged_ids), encoding="utf-8")
print(f"Wrote judged_204.txt ({len(judged_ids)} doc-ids)")