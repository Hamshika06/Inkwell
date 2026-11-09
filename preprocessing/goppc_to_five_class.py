"""Turn GoPPC rows into clean five-class training rows.

Reads data/interim/goppc_train.jsonl and goppc_test.jsonl (written by goppc_preprocess.py)
and rebuilds each row's labels from its original annotation (`orig_label`) with
configs/goppc_mapping.json. The upstream test split is kept; a validation split is made
from whole train policies.

Example:
    python preprocessing/goppc_preprocess.py
    python preprocessing/goppc_preprocess.py --csv data/raw/goppc/p_dataset_document_test.csv
    python preprocessing/goppc_to_five_class.py

Steps, in order:
  1. Label tokens. Tokens that are not taxonomy IDs are repaired with `concept_fixes`
     (mostly missing commas, e.g. "1711" -> 17, 11). Unclear tokens count as unknown.
  2. Annotator agreement. `orig_label` holds one concept list per annotator, separated by
     ";". A class is positive when more than half of the annotators chose it. A class chosen
     by some but not most annotators is unknown (mask 0), not negative.
  3. Unknown concepts. On rows with NON-GDPR (18.x) or UNKNOWN (19) concepts, or an unclear
     or unlisted token, every class that is not positive is unknown (mask 0). Controller,
     representative and DPO concepts (1-3) are real negatives.
  4. Text clean-up: broken UTF-8 sequences are repaired, invisible characters are removed.
  5. Length. Rows under --min-words words (default 5) are dropped; unlabelled rows under
     --min-unlabelled-words (default 8) are dropped; rows over --max-words (default 300) are
     dropped, because GoPPC has no spans to split them with correct labels.
  6. Rows with no positive and no known class carry no training signal and are dropped.
  7. Repeated text. Rows with the same text in the same split are merged into one: a class
     is positive or negative only when every copy agrees, otherwise unknown.
  8. Validation split. Whole train policies (doc_id, recovered from the GoPPC-150 XML files)
     are moved to validation: about --val-frac of train rows, with at least --min-val-pos
     positives per class.
  9. Leakage. Rows sharing at least half their 8-word phrases with a row in a later split
     (train < validation < test) are dropped from the earlier split, checked within GoPPC and
     against OPP-115 and PolicyIE. OPP-115/PolicyIE rows are never dropped here; the ones that
     copy GoPPC evaluation rows are listed in other_rows_to_drop.csv for the combine step.
"""
import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_integration.combine_opp115_c3pa import shingles, text_key  # same rules as the combine step

NEAR_DUP = 0.5
SPLIT_RANK = {"train": 0, "validation": 1, "test": 2}
MOJIBAKE = [("â€™", "’"), ("â€˜", "‘"), ("â€œ", "“"), ("â€\x9d", "”"), ("â€“", "–"),
            ("â€”", "—"), ("â€", "”")]
INVISIBLE = re.compile("[​-‏‪-‮⁠﻿]")


def clean(text):
    for bad, good in MOJIBAKE:
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", INVISIBLE.sub("", text)).strip()


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    classes, mapping = cfg["classes"], cfg["concept_id_to_class"]
    if len(classes) != 5 or len(set(classes)) != 5:
        raise SystemExit("Mapping config must define exactly five unique classes")
    if set(mapping.values()) - set(classes):
        raise SystemExit("Unknown target classes in concept_id_to_class")
    unknown, negative = set(cfg.get("unknown_concepts", [])), set(cfg.get("negative_concepts", []))
    fixes = {k: v for k, v in cfg.get("concept_fixes", {}).items() if k != "note"}
    overlap = (set(mapping) & (unknown | negative)) | (unknown & negative)
    if overlap:
        raise SystemExit(f"Concepts listed twice in the config: {sorted(overlap)}")
    return classes, mapping, unknown, negative, fixes


def label_row(orig_label, classes, mapping, unknown, negative, fixes, stats):
    """(label_vec, label_mask, annotator concept lists) from the raw `label` field."""
    groups, uncertain = [], False
    for group in (orig_label or "").split(";"):
        concepts = set()
        for tok in (t.strip() for t in group.split(",")):
            if not tok:
                continue
            if tok in fixes:
                stats["tokens_fixed" if fixes[tok] else "tokens_unclear"] += 1
                uncertain |= not fixes[tok]
                concepts.update(fixes[tok])
            else:
                concepts.add(tok)
        for c in concepts:
            if c in unknown:
                uncertain = True
            elif c not in mapping and c not in negative:
                stats[f"unlisted_concept:{c}"] += 1
                uncertain = True
        groups.append(concepts)
    groups = [g for g in groups if g]
    if not groups:
        return None, None, groups
    votes = Counter(cls for g in groups for cls in {mapping[c] for c in g if c in mapping})
    vec, mask = [], []
    for cls in classes:
        n = votes[cls]
        positive = 2 * n > len(groups)
        vec.append(int(positive))
        mask.append(int(positive or (n == 0 and not uncertain)))
        if n and not positive:
            stats[f"disagreement_masked:{cls}"] += 1
    return vec, mask, [sorted(g) for g in groups]


def merge_copies(rows, classes):
    """One row per text: a class is known only when every copy agrees on it."""
    out = dict(rows[0])
    vec, mask = [], []
    for i in range(len(classes)):
        states = {(r["label_vec"][i], r["label_mask"][i]) for r in rows}
        if len(states) == 1 and next(iter(states))[1] == 1:
            v, m = next(iter(states))
        else:
            v, m = 0, 0
        vec.append(v)
        mask.append(m)
    out.update(label_vec=vec, label_mask=mask,
               labels=[c for c, v in zip(classes, vec) if v],
               merged_ids=[r["id"] for r in rows])
    return out


def make_validation(rows, classes, frac, min_pos, seed):
    """Move whole train policies to validation. Returns (policies, seed used)."""
    by_doc = defaultdict(list)
    for r in rows:
        if r["split"] == "train":
            if not r["doc_id"]:
                raise SystemExit(f"{r['id']} has no doc_id; re-run goppc_preprocess.py with --xml-dir")
            by_doc[r["doc_id"]].append(r)
    target = frac * sum(len(v) for v in by_doc.values())
    for s in range(seed, seed + 1000):
        docs = sorted(by_doc)
        random.Random(s).shuffle(docs)
        picked, n = [], 0
        for d in docs:
            if n >= target:
                break
            picked.append(d)
            n += len(by_doc[d])
        if all(sum(r["label_vec"][i] for d in picked for r in by_doc[d]) >= min_pos
               for i in range(len(classes))):
            return sorted(picked), s
    raise SystemExit("Could not find a validation set with enough positives per class")


def find_leaks(goppc_rows, other_rows):
    """(lower_row, higher_row, share) for every pair across splits that repeats text."""
    rows = goppc_rows + other_rows
    n_g = len(goppc_rows)
    sh = [shingles(r["text"]) for r in rows]
    keys = [text_key(r["text"]) for r in rows]
    index, by_key = defaultdict(set), defaultdict(list)
    for i, s in enumerate(sh):
        for g in s:
            index[g].add(i)
    for i, k in enumerate(keys):
        by_key[k].append(i)
    leaks = []
    for i in range(n_g):  # every pair involves at least one GoPPC row
        hits = {j: n / max(1, min(len(sh[i]), len(sh[j])))
                for j, n in Counter(j for g in sh[i] for j in index[g] if j != i).items()}
        hits.update({j: 1.0 for j in by_key[keys[i]] if j != i})
        for j, share in hits.items():
            if share < NEAR_DUP or (j < n_g and j < i):
                continue  # each GoPPC pair once
            ri, rj = SPLIT_RANK[rows[i]["split"]], SPLIT_RANK[rows[j]["split"]]
            if ri == rj:
                continue
            low, high = (rows[i], rows[j]) if ri < rj else (rows[j], rows[i])
            leaks.append((low, high, round(share, 2)))
    return leaks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", nargs="+",
                    default=[ROOT / "data/interim/goppc_train.jsonl", ROOT / "data/interim/goppc_test.jsonl"])
    ap.add_argument("--mapping", default=ROOT / "configs/goppc_mapping.json")
    ap.add_argument("--opp115", default=ROOT / "data/interim/opp115_five_class.jsonl")
    ap.add_argument("--policyie", default=ROOT / "data/interim/policyie_five_class.jsonl")
    ap.add_argument("--out", default=ROOT / "data/interim/goppc_five_class.jsonl")
    ap.add_argument("--report-dir", default=ROOT / "preprocessing/reports/goppc_five_class")
    ap.add_argument("--min-words", type=int, default=5)
    ap.add_argument("--min-unlabelled-words", type=int, default=8)
    ap.add_argument("--max-words", type=int, default=300)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--min-val-pos", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    classes, mapping, unknown, negative, fixes = load_config(args.mapping)
    rep_dir = Path(args.report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)
    stats, dropped = Counter(), []
    src = []
    for p in args.inp:
        if not Path(p).exists():
            raise SystemExit(f"Input not found: {p} (run goppc_preprocess.py for that split)")
        src += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    stats["input_rows"] = len(src)

    def drop(r, reason, extra=""):
        dropped.append((r["id"], reason, extra, r["text"][:200]))
        stats[f"dropped:{reason}"] += 1

    # 1-6: labels, text, length
    rows = []
    for s in src:
        vec, mask, groups = label_row(s["orig_label"], classes, mapping, unknown, negative, fixes, stats)
        r = {
            "id": s["unit_id"],
            "source": "goppc",
            "doc_id": s.get("doc_id"),
            "group_id": s.get("group_id"),
            "split": s["split"],
            "text": s["text"],
            "labels": [c for c, v in zip(classes, vec or []) if v],
            "label_vec": vec,
            "label_mask": mask,
            "label_fractions": None,
            "orig_label": s["orig_label"],
            "annotator_concepts": groups,
            "website": (s.get("metadata") or {}).get("website"),
        }
        before = r["text"]
        r["text"] = clean(r["text"])
        if r["text"] != before:
            stats["rows_text_repaired"] += 1
        n = len(r["text"].split())
        if vec is None:
            drop(r, "no label tokens")
        elif n < args.min_words:
            drop(r, f"under {args.min_words} words")
        elif n < args.min_unlabelled_words and not r["labels"]:
            drop(r, f"unlabelled and under {args.min_unlabelled_words} words")
        elif n > args.max_words:
            drop(r, f"over {args.max_words} words")
        elif not any(mask):
            drop(r, "no known class")
        else:
            rows.append(r)

    # 7: repeated text (within a split; across splits is leakage, step 9)
    by_text = defaultdict(list)
    for r in rows:
        by_text[(r["split"], text_key(r["text"]))].append(r)
    merged = []
    for group in by_text.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        m = merge_copies(group, classes)
        stats["repeated_text_groups_merged"] += 1
        stats["rows_removed_by_merge"] += len(group) - 1
        if not any(m["label_mask"]):
            drop(m, "repeated text with conflicting labels")
        else:
            merged.append(m)

    # 8: validation split from whole train policies
    val_docs, used_seed = make_validation(merged, classes, args.val_frac, args.min_val_pos, args.seed)
    for r in merged:
        if r["split"] == "train" and r["doc_id"] in val_docs:
            r["split"] = "validation"
    doc_splits = defaultdict(set)
    for r in merged:
        doc_splits[r["doc_id"]].add(r["split"])
    assert all(len(s) == 1 for s in doc_splits.values()), "a policy spans more than one split"

    # 9: leakage within GoPPC and against OPP-115 / PolicyIE
    others = []
    for p in (args.opp115, args.policyie):
        if p and Path(p).exists():
            others += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        else:
            print(f"warning: {p} not found; leakage against it not checked")
    goppc_drop, other_drop = {}, {}
    for low, high, share in find_leaks(merged, others):
        target = goppc_drop if low["source"] == "goppc" else other_drop
        target.setdefault(low["id"], (low, high, share))
    for low, high, share in goppc_drop.values():
        drop(low, f"near-copy of {high['source']} {high['split']} row", f"{high['id']} ({share})")
    out_rows = [r for r in merged if r["id"] not in goppc_drop]

    assert all(m for r in out_rows for v, m in zip(r["label_vec"], r["label_mask"]) if v)
    assert len({r["id"] for r in out_rows}) == len(out_rows)
    with open(rep_dir / "other_rows_to_drop.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "source", "split", "goppc_id", "goppc_split", "share"),
                                 *[(l["id"], l["source"], l["split"], h["id"], h["split"], s)
                                   for l, h, s in sorted(other_drop.values(), key=lambda x: x[0]["id"])]])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(rep_dir / "dropped_rows.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "reason", "matched_row", "text_start"), *dropped])

    splits = sorted({r["split"] for r in out_rows}, key=SPLIT_RANK.get)
    pos = {s: Counter(c for r in out_rows if r["split"] == s for c in r["labels"]) for s in splits}
    known = {s: Counter(c for r in out_rows if r["split"] == s
                        for c, m in zip(classes, r["label_mask"]) if m) for s in splits}
    words = sorted(len(r["text"].split()) for r in out_rows)
    sites = lambda s: sorted({r["website"] or r["doc_id"] for r in out_rows if r["split"] == s})
    report = {
        "input_files": [str(p) for p in args.inp],
        "output_file": str(out_path),
        "classes": classes,
        "rows_in": len(src),
        "rows_out": len(out_rows),
        "rows_by_split": {s: sum(1 for r in out_rows if r["split"] == s) for s in splits},
        "policies_by_split": {s: len({r["doc_id"] for r in out_rows if r["split"] == s}) for s in splits},
        "validation_policies": {"seed": used_seed, "websites": sites("validation")},
        "test_policies": sites("test"),
        "other_source_rows_to_drop_in_combine": len(other_drop),
        "steps": {k: v for k, v in sorted(stats.items()) if k != "input_rows"},
        "positives_by_class_and_split": {s: {c: pos[s][c] for c in classes} for s in splits},
        "known_rows_by_class_and_split (mask = 1)": {s: {c: known[s][c] for c in classes} for s in splits},
        "rows_with_no_class": sum(1 for r in out_rows if not r["labels"]),
        "rows_with_all_classes_known": sum(1 for r in out_rows if all(r["label_mask"])),
        "words": {"min": words[0], "median": words[len(words) // 2], "max": words[-1]},
        "mask_patterns": dict(Counter(str(r["label_mask"]) for r in out_rows).most_common(10)),
        "notes": [
            "A class is positive when more than half of the annotators chose it; partial agreement is masked.",
            "Rows with NON-GDPR (18.x) / UNKNOWN (19) or unclear concepts have non-positive classes masked.",
            "Training loss must apply label_mask, or masked classes become false negatives.",
        ],
    }
    (rep_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("rows_in", "rows_out", "rows_by_split", "policies_by_split",
                                             "validation_policies", "other_source_rows_to_drop_in_combine",
                                             "steps", "positives_by_class_and_split", "words")}, indent=2))


if __name__ == "__main__":
    main()
