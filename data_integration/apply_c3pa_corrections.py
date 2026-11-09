#!/usr/bin/env python3
"""
Apply label_corrections.csv to the cleaned C3PA units and write a reviewed copy.

Usage:
    python data_integration/apply_c3pa_corrections.py
    python data_integration/apply_c3pa_corrections.py --src data/interim/c3pa_v2 --out data/interim/c3pa_v2_reviewed

corrections CSV columns: unit_id, action (DROP | SET), labels_after ('|'-separated for SET), reason, reviewed_by.
DROP removes the unit; SET replaces its labels (every label must be in configs/label_schema.json).
Unit ids not found in the source are an error. Writes c3pa.jsonl, change_log.csv and review_report.txt.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = json.loads((ROOT / "configs" / "label_schema.json").read_text())["categories"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(ROOT / "data/interim/c3pa_v2"))
    ap.add_argument("--out", default=str(ROOT / "data/interim/c3pa_v2_reviewed"))
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new --out")
    units = [json.loads(l) for l in open(src / "c3pa.jsonl", encoding="utf-8") if l.strip()]
    by_id = {u["unit_id"]: u for u in units}
    fixes = {}
    with open(src / "label_corrections.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["unit_id"] not in by_id: raise SystemExit(f"unknown unit {r['unit_id']}")
            if r["unit_id"] in fixes: raise SystemExit(f"duplicate correction for {r['unit_id']}")
            if r["action"] == "SET":
                new = [l for l in r["labels_after"].split("|") if l]
                if not new or not set(new) <= set(CATEGORIES): raise SystemExit(f"bad labels for {r['unit_id']}: {new}")
            elif r["action"] != "DROP": raise SystemExit(f"bad action for {r['unit_id']}")
            fixes[r["unit_id"]] = r
    kept, log = [], []
    for u in units:
        r = fixes.get(u["unit_id"])
        if r is None: kept.append(u); continue
        if r["action"] == "DROP":
            log.append((u["unit_id"], "DROP", "|".join(u["labels"]), "", r["reason"])); continue
        new = [c for c in CATEGORIES if c in r["labels_after"].split("|")]  # schema order
        log.append((u["unit_id"], "SET", "|".join(u["labels"]), "|".join(new), r["reason"]))
        kept.append({**u, "labels": new, "label_mask": [1 if c in new else 0 for c in CATEGORIES],
                     "orig_labels_before_review": u["labels"]})
    out.mkdir(parents=True)
    (out / "c3pa.jsonl").write_bytes("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in kept).encode("utf-8"))
    with open(out / "change_log.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["unit_id", "action", "labels_before", "labels_after", "reason"]); w.writerows(log)
    cnt = lambda rows: Counter(l for u in rows for l in u["labels"])
    b, a = cnt(units), cnt(kept)
    lines = [f"source {src}", f"units before {len(units)}  after {len(kept)}  dropped {sum(x[1] == 'DROP' for x in log)}  relabeled {sum(x[1] == 'SET' for x in log)}",
             "label counts before -> after:"] + [f"  {c:40s} {b[c]:6d} -> {a[c]:6d}" for c in CATEGORIES if b[c] or a[c]]
    (out / "review_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8"); print("\n".join(lines))


if __name__ == "__main__":
    main()
