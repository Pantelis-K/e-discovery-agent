from pathlib import Path
import json
import time

# Run from data/raw/
raw_root = Path(".")

# §5 enumeration trap: the .zip suffix on custodian directories is a naming
# artefact — they're plain directories. Globbing *.zip DIRECTORIES catches the
# split kaminski-v / kean-s parts. A *_xml.zip glob would silently drop 60,723
# files across those two custodians.
custodian_dirs = [d for d in raw_root.glob("*.zip") if d.is_dir()]
print(f"Custodian directories: {len(custodian_dirs)}  (expect 159)")
assert len(custodian_dirs) == 159, f"Custodian count mismatch — got {len(custodian_dirs)}"

index = {}
total_files = 0
attach_files = 0
t0 = time.time()

for cd in custodian_dirs:
    for txt_file in cd.rglob("*.txt"):
        total_files += 1
        stem = txt_file.stem
        segs = stem.split(".")
        if len(segs) >= 4 and segs[-1].isdigit():
            attach_files += 1
            continue
        index[stem] = str(txt_file)

print(f"Total .txt files walked:  {total_files:,}  (expect 685,592)")
print(f"Attachments (excluded):   {attach_files:,}")
print(f"Base emails in index:     {len(index):,}  (expect ~455,449)")
print(f"Walk time:                {time.time()-t0:.1f}s")

with open("doc_id_index.json", "w", encoding="utf-8") as f:
    json.dump(index, f)
print(f"Wrote doc_id_index.json ({len(index):,} entries)")

# Disk-join verification against judged 204
judged = Path("judged_204.txt").read_text(encoding="utf-8").splitlines()
found = sum(1 for d in judged if d in index)
missing = [d for d in judged if d not in index]

print(f"\n--- Disk-join verification ---")
print(f"Judged 204 doc-ids:  {len(judged):,}  (expect 2,028)")
print(f"  Found on disk:     {found:,}  ({100*found/len(judged):.1f}%)")
print(f"  Missing:           {len(missing)}")
if missing:
    print(f"  First 5 missing:   {missing[:5]}")