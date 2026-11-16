"""Combine the OPP-115, PolicyIE and GoPPC five-class files into one dataset.

Run the three preprocessing scripts first (each one checks leakage against the others'
output files, so this order leaves none):
    python preprocessing/policyie_to_five_class.py
    python preprocessing/goppc_to_five_class.py
    python preprocessing/opp115_to_five_class.py
    python data_integration/combine_five_class.py

Outputs (default folder data/processed_five_class/):
    combined_classifier.jsonl   every row, all splits
    train.jsonl, validation.jsonl, test.jsonl
    manifest.json               mapping, row/positive/known counts, train pos_weight per class
    combine_report.txt          the same counts as text, plus PASS/FAIL checks

What it does:
  * Keeps each source's split as it is (no rows move between splits).
  * Drops rows that a preprocessing script listed in its other_rows_to_drop.csv (rows of
    another source that copy one of its evaluation rows), if any are still present.
  * Merges rows with the same text in the same split across sources: a class is known only
    if every copy that knows it agrees; a conflict makes it unknown (mask 0).
  * Writes the shared fields at the top level and everything source-specific under "meta".
  * Checks: ids unique, vectors match labels, no positive on a masked class, each policy in
    one split, and no near-copy (>= half the 8-word phrases) between different splits.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_integration.combine_opp115_c3pa import shingles, text_key  # same rules as preprocessing

SOURCES = {  # priority order: the first source's row is kept when texts are merged
    "opp115": ROOT / "data/interim/opp115_five_class.jsonl",
    "policyie": ROOT / "data/interim/policyie_five_class.jsonl",
    "goppc": ROOT / "data/interim/goppc_five_class.jsonl",
}
DROP_LISTS = [
    ROOT / "preprocessing/reports/policyie_five_class/other_rows_to_drop.csv",
    ROOT / "preprocessing/reports/goppc_five_class/other_rows_to_drop.csv",
]
SPLITS = ["train", "validation", "test"]
CORE = ["id", "source", "doc_id", "group_id", "split", "text", "labels", "label_vec", "label_mask"]
NEAR_DUP = 0.5


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def to_shared(r):
    out = {k: r.get(k) for k in CORE}
    out["group_id"] = out["group_id"] or out["doc_id"]
    out["meta"] = {k: v for k, v in r.items() if k not in CORE}
    return out


def merge_copies(rows, classes):
    base = dict(rows[0])
    vec, mask = [], []
    for i in range(len(classes)):
        known = {r["label_vec"][i] for r in rows if r["label_mask"][i]}
        if len(known) == 1:
            vec.append(known.pop())
            mask.append(1)
        else:  # nobody knows it, or the copies disagree
            vec.append(0)
            mask.append(0)
    base.update(label_vec=vec, label_mask=mask, labels=[c for c, v in zip(classes, vec) if v])
    base["meta"] = dict(base["meta"], merged_ids=[r["id"] for r in rows],
                        merged_sources=sorted({r["source"] for r in rows}))
    return base


def cross_split_pairs(rows):
    sh = [shingles(r["text"]) for r in rows]
    index, by_key = defaultdict(set), defaultdict(list)
    for i, s in enumerate(sh):
        for g in s:
            index[g].add(i)
    for i, r in enumerate(rows):
        by_key[text_key(r["text"])].append(i)
    pairs = []
    for i, r in enumerate(rows):
        hits = {j for j, n in Counter(j for g in sh[i] for j in index[g] if j > i).items()
                if n / max(1, min(len(sh[i]), len(sh[j]))) >= NEAR_DUP}
        hits |= {j for j in by_key[text_key(r["text"])] if j > i}
        pairs += [(r["id"], rows[j]["id"]) for j in hits if rows[j]["split"] != r["split"]]
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opp115", default=SOURCES["opp115"])
    ap.add_argument("--policyie", default=SOURCES["policyie"])
    ap.add_argument("--goppc", default=SOURCES["goppc"])
    ap.add_argument("--mapping", default=ROOT / "configs/five_class_mapping.json")
    ap.add_argument("--out-dir", default=ROOT / "data/processed_five_class")
    ap.add_argument("--skip-leak-check", action="store_true", help="skip the slow near-copy check")
    args = ap.parse_args()

    classes = json.loads(Path(args.mapping).read_text(encoding="utf-8"))["classes"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines, checks, stats = [], [], Counter()
    say = lambda s="": lines.append(s)

    def check(name, ok, detail=""):
        checks.append((name, bool(ok)))
        say(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))

    # read
    rows = []
    for name, path in (("opp115", args.opp115), ("policyie", args.policyie), ("goppc", args.goppc)):
        if not Path(path).exists():
            raise SystemExit(f"Missing {path}; run the {name} preprocessing script first")
        got = [to_shared(r) for r in read_jsonl(path)]
        if {r["source"] for r in got} != {name}:
            raise SystemExit(f"{path} has rows from other sources: {sorted({r['source'] for r in got})}")
        stats[f"read:{name}"] = len(got)
        rows += got

    # drop rows listed by other preprocessing scripts
    to_drop = set()
    for p in DROP_LISTS:
        if p.exists():
            with open(p, encoding="utf-8", newline="") as f:
                to_drop |= {r["id"] for r in csv.DictReader(f)}
    present = [r for r in rows if r["id"] in to_drop]
    stats["dropped_from_other_rows_to_drop_lists"] = len(present)
    rows = [r for r in rows if r["id"] not in to_drop]

    # merge the same text in the same split across sources
    groups = defaultdict(list)
    for r in rows:
        groups[(r["split"], text_key(r["text"]))].append(r)
    priority = list(SOURCES)
    merged = []
    for g in groups.values():
        g.sort(key=lambda r: priority.index(r["source"]))
        if len(g) == 1:
            merged.append(g[0])
            continue
        m = merge_copies(g, classes)
        stats["same_text_groups_merged"] += 1
        stats["rows_removed_by_merge"] += len(g) - 1
        if any(m["label_mask"]) or m["labels"]:
            merged.append(m)
        else:
            stats["merged_rows_dropped_no_known_class"] += 1
    rows = sorted(merged, key=lambda r: (SPLITS.index(r["split"]), priority.index(r["source"]), r["id"]))

    # checks
    say("CHECKS")
    check("every row has a known split", all(r["split"] in SPLITS for r in rows))
    check("ids are unique", len({r["id"] for r in rows}) == len(rows))
    check("label vectors and masks have 5 entries",
          all(len(r["label_vec"]) == len(r["label_mask"]) == len(classes) for r in rows))
    check("labels match label vectors",
          all(r["labels"] == [c for c, v in zip(classes, r["label_vec"]) if v] for r in rows))
    check("no positive label on a masked class",
          all(m for r in rows for v, m in zip(r["label_vec"], r["label_mask"]) if v))
    doc_splits = defaultdict(set)
    for r in rows:
        doc_splits[r["doc_id"]].add(r["split"])
    spread = [d for d, s in doc_splits.items() if len(s) > 1]
    check("each policy is in one split", not spread, f"{len(spread)} policies span splits" if spread else "")
    check("every row has text", all(r["text"].strip() for r in rows))
    if args.skip_leak_check:
        say("[SKIP] no near-copies between splits")
    else:
        pairs = cross_split_pairs(rows)
        check("no near-copies between splits", not pairs,
              f"{len(pairs)} pairs, e.g. {pairs[:3]}" if pairs else "")

    # counts
    by = lambda pred: {s: sum(1 for r in rows if r["split"] == s and pred(r)) for s in SPLITS}
    rows_by = {src: by(lambda r, src=src: r["source"] == src) for src in SOURCES}
    pos = {c: {s: sum(r["label_vec"][i] for r in rows if r["split"] == s) for s in SPLITS}
           for i, c in enumerate(classes)}
    known = {c: {s: sum(r["label_mask"][i] for r in rows if r["split"] == s) for s in SPLITS}
             for i, c in enumerate(classes)}
    by_source = {c: {src: {s: sum(r["label_vec"][i] for r in rows if r["split"] == s and r["source"] == src)
                           for s in SPLITS} for src in SOURCES} for i, c in enumerate(classes)}
    pos_weight = {c: round((known[c]["train"] - pos[c]["train"]) / max(1, pos[c]["train"]), 3)
                  for c in classes}

    say()
    say("ROWS PER SOURCE AND SPLIT")
    for src in SOURCES:
        say(f"  {src:9s} " + "  ".join(f"{s}={rows_by[src][s]:5d}" for s in SPLITS)
            + f"  total={sum(rows_by[src].values())}")
    say(f"  {'all':9s} " + "  ".join(f"{s}={sum(rows_by[x][s] for x in SOURCES):5d}" for s in SPLITS)
        + f"  total={len(rows)}")
    say()
    say("POSITIVE / KNOWN ROWS PER CLASS AND SPLIT")
    for c in classes:
        say(f"  {c:27s} " + "  ".join(f"{s}={pos[c][s]:5d}/{known[c][s]:<5d}" for s in SPLITS))
    say(f"  {'(no class)':27s} " + "  ".join(f"{s}={by(lambda r: not r['labels'])[s]:5d}" for s in SPLITS))
    say()
    say("TRAIN POSITIVES PER CLASS BY SOURCE")
    for c in classes:
        say(f"  {c:27s} " + "  ".join(f"{src}={by_source[c][src]['train']:5d}" for src in SOURCES))
    say()
    say("SUGGESTED pos_weight FOR BCEWithLogitsLoss (train known negatives / positives)")
    say("  " + json.dumps(pos_weight))
    say()
    say("STEPS")
    for k, v in sorted(stats.items()):
        say(f"  {k}: {v}")

    # write
    for s in SPLITS:
        with open(out_dir / f"{s}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                if r["split"] == s:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out_dir / "combined_classifier.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "classes": classes,
        "inputs": {k: str(v) for k, v in (("opp115", args.opp115), ("policyie", args.policyie),
                                           ("goppc", args.goppc))},
        "mappings": {
            "opp115_and_policyie": "configs/five_class_mapping.json (via configs/policyie_mapping.json for PolicyIE)",
            "goppc": "configs/goppc_mapping.json",
        },
        "rows": len(rows),
        "rows_by_source_and_split": rows_by,
        "positives_by_class_and_split": pos,
        "known_by_class_and_split": known,
        "train_positives_by_class_and_source": {c: {src: by_source[c][src]["train"] for src in SOURCES}
                                                for c in classes},
        "train_pos_weight": pos_weight,
        "steps": dict(stats),
        "checks": {name: ok for name, ok in checks},
        "notes": [
            "label_mask 0 means the class was not annotated for that row: exclude it from the loss.",
            "pos_weight counts only rows where the class is known.",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    (out_dir / "combine_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if not all(ok for _, ok in checks):
        raise SystemExit("Some checks failed; see combine_report.txt")


if __name__ == "__main__":
    main()
