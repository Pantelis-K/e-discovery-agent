from pathlib import Path

# Load Topic 204 base rows from seed.csv (column 2 = topic, column 4 = canonical doc-id)
seed_204_base = set()
with Path("seed.csv").open(encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split(",")
        if len(parts) != 4:
            continue
        _, topic, _, canonical = parts
        if topic != "204":
            continue
        segs = canonical.split(".")
        if len(segs) >= 4 and segs[-1].isdigit():  # drop .N attachments
            continue
        seed_204_base.add(canonical)

judged_204 = set(Path("judged_204.txt").read_text(encoding="utf-8").splitlines())

overlap = sorted(seed_204_base & judged_204)
Path("overlap_excluded.txt").write_text("\n".join(overlap) + "\n", encoding="utf-8")
print(f"Wrote overlap_excluded.txt ({len(overlap)} doc-ids)")