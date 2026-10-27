"""
Usage (from the repository root):
    python preprocessing/policyie_preprocess.py --zip path/to/sanitized_split.zip

Source: https://github.com/wasiahmad/PolicyIE (MIT licence). Each N.txt is one paragraph; the
E lines in N.ann name the practices annotated in it. A paragraph can have several practices,
and a paragraph with none is a real negative for the four covered categories.
Hand-reviewed corrections listed in configs/policyie_mapping.json are applied after mapping.

Outputs:
    data/interim/policyie.jsonl              one row per paragraph
    preprocessing/reports/policyie/
      report.txt             counts and checks
      retention_review.csv   every Data Retention row, flagged when it reads like a user's right to
                             delete (OPP-115 files that under User Access, Edit and Deletion)
      opp115_overlap.csv     paragraphs that repeat OPP-115 text (the combine step should drop them)
"""
import argparse
import csv
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_integration.combine_opp115_c3pa import CATEGORIES, shingles, text_key  # same rules as the combine step

CONFIG = json.loads((ROOT / "configs/policyie_mapping.json").read_text())
MAPPING, FIXES = CONFIG["policyie_to_opp115"], CONFIG["corrections"]
COVERED = [c for c in CATEGORIES if c in MAPPING.values()]
LABEL_MASK = [int(c in COVERED) for c in CATEGORIES]  # 0 = PolicyIE says nothing about this category
MIN_WORDS = 5     # same as the C3PA script: shorter paragraphs are headings
NEAR_DUP = 0.5    # same as the combine step
USER_DELETION = (re.compile(r"\b(delete|deletion|erase|erasure|remove)\b", re.I),
                 re.compile(r"\b(you may|you can|request|right to|contact us)\b", re.I))


def read_rows(zip_path):
    z = zipfile.ZipFile(zip_path)
    names = set(z.namelist())
    rows = []
    for name in sorted(n for n in names if n.endswith(".txt") and "__MACOSX" not in n):
        parts = name.split("/")  # sanitized_split/<train|test>/[weekN/]<policy>/<N>.txt
        subset, policy, number = parts[1], parts[-2], int(Path(name).stem)
        ann = z.read(name[:-4] + ".ann").decode("utf-8") if name[:-4] + ".ann" in names else ""
        practices = sorted({line.split("\t")[1].split(":")[0] for line in ann.splitlines() if line.startswith("E")})
        text = re.sub(r"\s+", " ", z.read(name).decode("utf-8")).strip()
        rows.append(dict(
            source="policyie",
            doc_id=f"policyie:{policy}",
            group_id=f"policyie:{policy}",
            unit_id=f"policyie:{policy}#{number:04d}",
            text=text,
            labels=[c for c in COVERED if c in {MAPPING[p] for p in practices}],
            label_mask=list(LABEL_MASK),
            spans=[],
            subset=subset,
            n_words=len(text.split()),
            orig_labels=practices,
        ))
    return rows


def apply_corrections(rows):
    """Ignore Data Retention on the reviewed rows; children's-privacy rows become Specific Audiences."""
    retention, audiences = "Data Retention", "International and Specific Audiences"
    children = set(FIXES["children_to_specific_audiences"])
    ignore = set(FIXES["ignore_retention"])
    by_id = {r["unit_id"]: r for r in rows}
    assert children | ignore <= set(by_id), f"Unknown ids: {sorted(children | ignore - set(by_id))}"
    for uid in children | ignore:
        r = by_id[uid]
        assert retention in r["labels"], f"{uid} has no Data Retention label to correct"
        r["labels"].remove(retention)
        r["label_mask"][CATEGORIES.index(retention)] = 0
        if uid in children:
            r["labels"] = [c for c in CATEGORIES if c in r["labels"] or c == audiences]
            r["label_mask"][CATEGORIES.index(audiences)] = 1
    return len(children), len(ignore)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="sanitized_split.zip from the PolicyIE repository")
    ap.add_argument("--out", default=ROOT / "preprocessing/reports/policyie", help="report folder")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = []
    say = lambda s="": (print(s), report.append(s))

    rows = read_rows(args.zip)
    unknown = {p for r in rows for p in r["orig_labels"]} - set(MAPPING)
    if unknown:
        raise SystemExit(f"Practices missing from configs/policyie_mapping.json: {sorted(unknown)}")
    say(f"Read {len(rows)} paragraphs from {len({r['doc_id'] for r in rows})} policies")

    short = [r for r in rows if r["n_words"] < MIN_WORDS]
    rows = [r for r in rows if r["n_words"] >= MIN_WORDS]
    say(f"Dropped {len(short)} paragraphs under {MIN_WORDS} words (headings)")
    n_children, n_ignore = apply_corrections(rows)
    say(f"Corrected {n_children} children's-privacy rows (Data Retention ignored, Specific Audiences added) "
        f"and ignored Data Retention on {n_ignore} more")

    opp = [json.loads(l) for l in (ROOT / "data/versions/v1/classifier.jsonl").open(encoding="utf-8")]
    opp = [r for r in opp if r["source"] == "opp115"]
    opp_keys = {text_key(r["text"]) for r in opp}
    opp_sh = set().union(*(shingles(r["text"]) for r in opp))
    overlap = []
    for r in rows:
        sh = shingles(r["text"])
        share = sum(h in opp_sh for h in sh) / len(sh) if sh else 0
        if text_key(r["text"]) in opp_keys or share >= NEAR_DUP:
            overlap.append((r["unit_id"], round(share, 2), r["text"][:200]))

    retention = []
    for r in rows:
        if "Data Retention" in r["labels"]:
            flag = all(p.search(r["text"]) for p in USER_DELETION)
            retention.append((r["unit_id"], flag, r["text"]))

    # Checks
    ids = [r["unit_id"] for r in rows]
    assert len(set(ids)) == len(ids), "unit_id not unique"
    assert len({text_key(r["text"]) for r in rows}) == len(rows), "duplicate text inside PolicyIE"
    assert all(len(r["label_mask"]) == len(CATEGORIES) for r in rows)
    assert all(r["label_mask"][CATEGORIES.index(c)] for r in rows for c in r["labels"]), "label on a masked category"
    for policy in {r["doc_id"] for r in rows}:
        assert len({r["subset"] for r in rows if r["doc_id"] == policy}) == 1, f"{policy} in two subsets"
    say("All checks passed.")

    say(f"\nKept {len(rows)} paragraphs: " + str(dict(Counter(r["subset"] for r in rows))))
    say(f"Covered categories (mask = 1): {COVERED}")
    say(f"Paragraphs with none of them (real negatives): {sum(not r['labels'] for r in rows)}")
    say(f"Paragraphs with 2 or more: {sum(len(r['labels']) > 1 for r in rows)}")
    say("Paragraphs per category: " + str({c: n for c in CATEGORIES if (n := sum(c in r["labels"] for r in rows))}))
    say(f"Data Retention rows that read like a user's right to delete: "
        f"{sum(f for _, f, _ in retention)} of {len(retention)} (see retention_review.csv)")
    say(f"Paragraphs repeating OPP-115 text: {len(overlap)} (see opp115_overlap.csv)")

    with (ROOT / "data/interim/policyie.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out / "retention_review.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("unit_id", "looks_like_user_deletion", "text"), *retention])
    with (out / "opp115_overlap.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("unit_id", "shared_phrase_share", "text_start"), *overlap])
    (out / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()