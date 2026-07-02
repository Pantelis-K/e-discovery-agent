from pathlib import Path

seed = Path("seed.csv")
by_topic = {}
attach_dropped = 0
seed_204_base = set()

with seed.open(encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split(",")
        if len(parts) != 4:
            continue
        _, topic, label, canonical = parts
        segs = canonical.split(".")
        if len(segs) >= 4 and segs[-1].isdigit():
            attach_dropped += 1
            continue
        d = by_topic.setdefault(topic, {"rel": 0, "nrel": 0})
        if label == "1":
            d["rel"] += 1
        elif label == "0":
            d["nrel"] += 1
        if topic == "204":
            seed_204_base.add(canonical)

for topic in sorted(by_topic):
    d = by_topic[topic]
    print(f"Topic {topic}: rel={d['rel']:>4}  nrel={d['nrel']:>5}  total={d['rel']+d['nrel']:>5}")
print(f"\nAttachment rows dropped: {attach_dropped}")

# Overlap with judged 204 (base emails)
judged_204 = set(Path("judged_204.txt").read_text(encoding="utf-8").splitlines())
overlap = seed_204_base & judged_204
print(f"\nTopic 204 overlap (seed base ∩ judged base): {len(overlap)}")
print(f"  seed base emails:   {len(seed_204_base)}")
print(f"  judged base emails: {len(judged_204)}")