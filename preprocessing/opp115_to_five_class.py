"""Collapse OPP-115's ten categories into the five broad classes and clean it for fine-tuning.

Reads the ten-class OPP-115 classifier rows and writes five-class rows using
configs/five_class_mapping.json. OPP-115's own train/validation/test split is kept; rows are
only removed, never moved.

Example:
    python preprocessing/opp115_to_five_class.py \
      --in data/interim/opp115_classifier.jsonl \
      --out data/interim/opp115_five_class.jsonl

Steps, in order:
  1. Five classes. A five-class label is positive when any of its ten-class labels is
     positive (the input labels are already the 2-of-3 annotator majority). "Other" maps to
     no class. OPP-115 annotated every category, so every class is known (mask 1).
     label_fractions for a five-class label is the highest fraction among its ten-class
     labels; this is a lower bound, as per-annotator votes are not in the input.
  2. Text clean-up: invisible characters are removed and whitespace is normalised.
  3. Headings. Rows under --min-words words (default 5) are dropped, and unlabelled rows
     under --min-unlabelled-words (default 8), the same rules as PolicyIE and GoPPC.
  4. Repeated text. Rows with the same text in the same split are merged into one; a class
     is positive or negative only when every copy agrees, otherwise unknown (mask 0).
  5. Leakage. Rows sharing at least half their 8-word phrases with a row in a later split
     (train < validation < test) are dropped from the earlier split. This is checked within
     OPP-115 (some policies are copies of each other, e.g. Amazon and IMDb) and against the
     PolicyIE and GoPPC five-class files when they exist. Rows are dropped here only from
     OPP-115; the other scripts drop their own rows.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_integration.combine_opp115_c3pa import shingles, text_key  # same rules as the combine step

NEAR_DUP = 0.5
SPLIT_RANK = {"train": 0, "validation": 1, "test": 2}
INVISIBLE = re.compile("[​-‏‪-‮⁠﻿]")


def load_mapping(path, schema_path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    classes, mapping = doc["classes"], doc["opp115_to_five_class"]
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))["categories"]
    if len(classes) != 5 or len(set(classes)) != 5:
        raise SystemExit("Mapping must define exactly five unique classes")
    if set(mapping) != set(schema):
        raise SystemExit(f"Mapping keys must equal the ten categories in {schema_path}: "
                         f"missing={sorted(set(schema) - set(mapping))} "
                         f"extra={sorted(set(mapping) - set(schema))}")
    bad = {v for v in mapping.values() if v is not None} - set(classes)
    if bad:
        raise SystemExit(f"Unknown target classes: {sorted(bad)}")
    return classes, mapping


def convert(row, classes, mapping):
    old = row.get("labels") or []
    unknown = [l for l in old if l not in mapping]
    if unknown:
        raise SystemExit(f"Row {row.get('policy_id')}#{row.get('segment_id')} has labels "
                         f"outside the schema: {unknown}")
    new = sorted({mapping[l] for l in old if mapping[l]}, key=classes.index)
    fractions = {}
    for label, frac in (row.get("label_fractions") or {}).items():
        target = mapping.get(label)
        if target:
            fractions[target] = max(fractions.get(target, 0.0), frac)
    policy_id = str(row["policy_id"])
    seg = int(row["segment_id"])
    doc_id = f"opp115:{policy_id}"
    return {
        "id": f"opp115:{policy_id}#{seg:04d}",
        "source": "opp115",
        "doc_id": doc_id,
        "group_id": doc_id,
        "split": row["split"],
        "text": re.sub(r"\s+", " ", INVISIBLE.sub("", row["text"])).strip(),
        "labels": new,
        "label_vec": [int(c in new) for c in classes],
        "label_mask": [1] * len(classes),
        "label_fractions": {c: fractions[c] for c in classes if c in fractions},
        "orig_labels": list(old),
        "orig_label_fractions": row.get("label_fractions") or {},
    }


def merge_copies(rows, classes):
    """One row per text: a class is known only when every copy agrees on it."""
    out = dict(rows[0])
    vec, mask = [], []
    for i in range(len(classes)):
        states = {(r["label_vec"][i], r["label_mask"][i]) for r in rows}
        v, m = next(iter(states)) if len(states) == 1 and next(iter(states))[1] else (0, 0)
        vec.append(v)
        mask.append(m)
    out.update(label_vec=vec, label_mask=mask, labels=[c for c, v in zip(classes, vec) if v],
               orig_labels=sorted({l for r in rows for l in r["orig_labels"]}),
               merged_ids=[r["id"] for r in rows])
    return out


def find_leaks(opp_rows, other_rows):
    """(lower_row, higher_row, share) for every pair across splits that involves OPP-115."""
    rows = opp_rows + other_rows
    n_o = len(opp_rows)
    sh = [shingles(r["text"]) for r in rows]
    keys = [text_key(r["text"]) for r in rows]
    index, by_key = defaultdict(set), defaultdict(list)
    for i, s in enumerate(sh):
        for g in s:
            index[g].add(i)
    for i, k in enumerate(keys):
        by_key[k].append(i)
    leaks = []
    for i in range(n_o):
        hits = {j: n / max(1, min(len(sh[i]), len(sh[j])))
                for j, n in Counter(j for g in sh[i] for j in index[g] if j != i).items()}
        hits.update({j: 1.0 for j in by_key[keys[i]] if j != i})
        for j, share in hits.items():
            if share < NEAR_DUP or (j < n_o and j < i):
                continue  # each OPP-115 pair once
            ri, rj = SPLIT_RANK[rows[i]["split"]], SPLIT_RANK[rows[j]["split"]]
            if ri == rj:
                continue
            low, high = (rows[i], rows[j]) if ri < rj else (rows[j], rows[i])
            leaks.append((low, high, round(share, 2)))
    return leaks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=ROOT / "data/interim/opp115_classifier.jsonl")
    ap.add_argument("--out", default=ROOT / "data/interim/opp115_five_class.jsonl")
    ap.add_argument("--mapping", default=ROOT / "configs/five_class_mapping.json")
    ap.add_argument("--schema", default=ROOT / "configs/label_schema.json")
    ap.add_argument("--policyie", default=ROOT / "data/interim/policyie_five_class.jsonl")
    ap.add_argument("--goppc", default=ROOT / "data/interim/goppc_five_class.jsonl")
    ap.add_argument("--report-dir", default=ROOT / "preprocessing/reports/opp115_five_class")
    ap.add_argument("--min-words", type=int, default=5)
    ap.add_argument("--min-unlabelled-words", type=int, default=8)
    args = ap.parse_args()

    classes, mapping = load_mapping(args.mapping, args.schema)
    rep_dir = Path(args.report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)
    stats, dropped = Counter(), []

    def drop(r, reason, extra=""):
        dropped.append((r["id"], r["split"], reason, extra, r["orig_labels"], r["text"][:200]))
        stats[f"dropped:{reason}"] += 1

    src = [json.loads(l) for l in open(args.inp, encoding="utf-8") if l.strip()]
    rows = [convert(r, classes, mapping) for r in src]
    if len({r["id"] for r in rows}) != len(rows):
        raise SystemExit("Duplicate ids in output")
    stats["rows_where_two_old_labels_merged"] = sum(
        1 for r in rows if len({l for l in r["orig_labels"] if mapping[l]}) > len(r["labels"]))

    # 3: headings
    kept = []
    for r in rows:
        n = len(r["text"].split())
        if n < args.min_words:
            drop(r, f"under {args.min_words} words")
        elif n < args.min_unlabelled_words and not r["labels"]:
            drop(r, f"unlabelled and under {args.min_unlabelled_words} words")
        else:
            kept.append(r)

    # 4: repeated text within a split
    groups = defaultdict(list)
    for r in kept:
        groups[(r["split"], text_key(r["text"]))].append(r)
    merged = []
    for g in groups.values():
        if len(g) == 1:
            merged.append(g[0])
            continue
        m = merge_copies(g, classes)
        stats["repeated_text_groups_merged"] += 1
        stats["rows_removed_by_merge"] += len(g) - 1
        if len({tuple(r["labels"]) for r in g}) > 1:
            stats["repeated_text_groups_with_conflicting_labels"] += 1
        if not any(m["label_mask"]):
            drop(m, "repeated text with conflicting labels on every class")
        else:
            merged.append(m)

    # 5: leakage within OPP-115 and against PolicyIE / GoPPC
    others = []
    for p in (args.policyie, args.goppc):
        if p and Path(p).exists():
            others += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        else:
            print(f"warning: {p} not found; leakage against it not checked")
    leaked = {}
    for low, high, share in find_leaks(merged, others):
        if low["source"] == "opp115":
            leaked.setdefault(low["id"], (low, high, share))
    for low, high, share in leaked.values():
        drop(low, f"near-copy of {high['source']} {high['split']} row", f"{high['id']} ({share})")
    out_rows = [r for r in merged if r["id"] not in leaked]
    assert all(m for r in out_rows for v, m in zip(r["label_vec"], r["label_mask"]) if v)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(rep_dir / "dropped_rows.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "split", "reason", "matched_row", "orig_labels", "text_start"),
                                 *[(a, b, c, d, "|".join(e), t) for a, b, c, d, e, t in dropped]])

    splits = sorted({r["split"] for r in out_rows}, key=SPLIT_RANK.get)
    pos = {s: Counter(c for r in out_rows if r["split"] == s for c in r["labels"]) for s in splits}
    old_by_new = {c: Counter() for c in classes}
    for r in out_rows:
        for l in r["orig_labels"]:
            if mapping[l]:
                old_by_new[mapping[l]][l] += 1
    report = {
        "input_file": str(args.inp),
        "output_file": str(out_path),
        "classes": classes,
        "mapping": mapping,
        "rows_in": len(src),
        "rows_out": len(out_rows),
        "rows_in_by_split": dict(Counter(r["split"] for r in rows)),
        "rows_by_split": {s: sum(1 for r in out_rows if r["split"] == s) for s in splits},
        "policies_by_split": {s: len({r["doc_id"] for r in out_rows if r["split"] == s}) for s in splits},
        "steps": dict(sorted(stats.items())),
        "rows_with_no_class": sum(1 for r in out_rows if not r["labels"]),
        "rows_with_a_masked_class": sum(1 for r in out_rows if not all(r["label_mask"])),
        "positives_by_class_and_split": {s: {c: pos[s][c] for c in classes} for s in splits},
        "ten_class_label_counts_feeding_each_class": {c: dict(old_by_new[c]) for c in classes},
        "notes": [
            "Positive if any source category is a 2-of-3 majority label; mask is all ones except merged conflicts.",
            "Rows labelled only 'Other' are kept with no class.",
            "label_fractions per five-class label is the max over its source categories (a lower bound).",
            "Validation/test rows are never dropped for leakage within OPP-115; the earlier-split copy is.",
        ],
    }
    (rep_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("rows_in", "rows_out", "rows_in_by_split", "rows_by_split",
                                             "steps", "positives_by_class_and_split")}, indent=2))


if __name__ == "__main__":
    main()
