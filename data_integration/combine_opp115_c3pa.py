#!/usr/bin/env python3
"""
Combine the preprocessed OPP-115 and C3PA datasets into one classifier file (and one
extraction file) for fine-tuning.

Usage:
    python combine_opp115_c3pa.py \
        --opp-dir Preprocessing_OPP115/output \
        --c3pa Preprocessing_C3PA/c3pa_preprocessing_output.zip \
        --opp-root OPP-115 \
        --out Combine_OPP115_C3PA/output

Inputs
    --opp-dir   folder with classifier_data.jsonl and extraction_data.jsonl from
                opp115_preprocess.py (already split by policy into train/validation/test)
    --c3pa      c3pa.jsonl, or the output zip that contains it (with label_schema.json)
    --opp-root  OPP-115 folder (or zip); only its annotations/ file NAMES are read, to get
                each policy's website domain so that companies can be kept in one split

What it does
    1. loads both datasets and puts them in one schema (10 OPP-115 categories, multi-hot
       label vector, label mask)
    2. removes C3PA units whose text also appears in OPP-115 (exact match, or >= 50% of
       their 8-word phrases) so no text is shared across sources
    3. splits: OPP-115 keeps its own train/validation/test policies. C3PA is split by
       company (never by unit). A C3PA company that is also an OPP-115 website gets that
       website's split. The rest are assigned at random by company with a fixed seed.
    4. writes combined_classifier.jsonl and combined_extraction.jsonl (only OPP-115 has
       span tags; C3PA has none)
    5. runs checks and exits with code 1 if any fail

Label mask (most important design choice)
    C3PA only contains text that annotators highlighted as relevant to a CCPA disclosure
    mandate, and covers 5 of the 10 categories. A missing label therefore means "not
    annotated", not "absent". --c3pa-mask positive (default) trains only on the labels a
    C3PA unit actually has; --c3pa-mask covered marks all 5 covered categories as known,
    so absent ones count as negatives (this is the C3PA script's original mask).
"""
import argparse
import csv
import io
import json
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = ["First Party Collection/Use", "Third Party Sharing/Collection", "User Choice/Control",
              "Data Security", "International and Specific Audiences", "User Access, Edit and Deletion",
              "Policy Change", "Data Retention", "Do Not Track", "Other"]
CAT_INDEX = {c: i for i, c in enumerate(CATEGORIES)}
SPLITS = ("train", "validation", "test")
SHINGLE = 8


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def text_key(s):
    """Duplicate-detection key: lowercase letters and digits only (same as the C3PA script)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def base_domain(d):
    """'https://www.Sports.Example.co.uk' style host -> 'example.co.uk' (rough registrable domain)."""
    d = (d or "").lower().strip().split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    parts = [p for p in d.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "ac", "gov", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def shingles(text):
    w = re.findall(r"\w+", text.lower())
    return {hash(" ".join(w[i:i + SHINGLE])) for i in range(len(w) - SHINGLE + 1)}


def read_jsonl(src):
    return [json.loads(line) for line in src if line.strip()]


def open_c3pa(path):
    """Return (records, schema_categories_or_None) from c3pa.jsonl or the output zip."""
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if not n.startswith("__MACOSX")]
            jl = next((n for n in names if n.endswith("c3pa.jsonl")), None)
            if jl is None:
                sys.exit("c3pa.jsonl not found inside the zip")
            recs = read_jsonl(io.TextIOWrapper(z.open(jl), encoding="utf-8"))
            sc = next((n for n in names if n.endswith("label_schema.json")), None)
            schema = json.loads(z.read(sc))["categories"] if sc else None
        return recs, schema
    with open(p, encoding="utf-8") as f:
        recs = read_jsonl(f)
    for sc in (p.parent.parent / "label_schema.json", p.parent.parent.parent / "configs" / "label_schema.json"):
        if sc.exists():
            return recs, json.loads(sc.read_text())["categories"]
    return recs, None


def docs_domains(path):
    """{policy prefix: base domain} from opp115_docs.csv (columns doc_id, domain)."""
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = base_domain(r.get("domain") or "")
            if d:
                out[r["doc_id"].split(":", 1)[1]] = d
    return out


def opp_domains(opp_root):
    """{policy prefix: base domain} from the annotation file names, e.g. 1017_sci-news.com.csv."""
    if not opp_root:
        return {}
    p = Path(opp_root)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if "/annotations/" in n and n.endswith(".csv")]
    else:
        base = p if (p / "annotations").exists() else p / "OPP-115"
        names = [str(f) for f in (base / "annotations").glob("*.csv")]
    out = {}
    for n in names:
        stem = Path(n).name[:-4]
        if "_" in stem:
            pre, dom = stem.split("_", 1)
            out[pre] = base_domain(dom)
    return out


def multi_hot(labels):
    v = [0] * len(CATEGORIES)
    for l in labels:
        v[CAT_INDEX[l]] = 1
    return v


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail="", warn=False):
        self.items.append((name, bool(ok), detail, warn))

    def lines(self):
        out = []
        for name, ok, detail, warn in self.items:
            tag = "PASS" if ok else ("WARN" if warn else "FAIL")
            out.append(f"[{tag}] {name}" + (f" -- {detail}" if detail else ""))
        return out

    @property
    def ok(self):
        return all(ok or warn for _, ok, _, warn in self.items)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opp-dir", required=True, help="output folder of opp115_preprocess.py")
    ap.add_argument("--c3pa", required=True, help="c3pa.jsonl or the C3PA output zip")
    ap.add_argument("--opp-root", default=None, help="OPP-115 folder/zip (for website domains)")
    ap.add_argument("--opp-docs", default=None,
                    help="opp115_docs.csv from the preprocessing reports (website domains; use instead of --opp-root)")
    ap.add_argument("--out", default="output")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--split", type=float, nargs=3, default=(0.8, 0.1, 0.1),
                    metavar=("TRAIN", "VAL", "TEST"), help="target shares for C3PA-only companies")
    ap.add_argument("--c3pa-mask", choices=["positive", "covered"], default="positive")
    ap.add_argument("--c3pa-weight", type=float, default=1.0, help="per-row weight stored for C3PA rows")
    ap.add_argument("--near-dup", type=float, default=0.5,
                    help="drop a C3PA unit if this share of its 8-word phrases occur in OPP-115")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = []

    def say(msg=""):
        print(msg)
        log.append(msg)

    # ---------------- load ----------------
    opp_dir = Path(args.opp_dir)
    def pick(*names):
        for n in names:
            if (opp_dir / n).exists():
                return opp_dir / n
        sys.exit(f"None of {names} found in {opp_dir}")

    opp_clf = read_jsonl(open(pick("classifier_data.jsonl", "opp115_classifier.jsonl"), encoding="utf-8"))
    opp_ext = read_jsonl(open(pick("extraction_data.jsonl", "opp115_extraction.jsonl"), encoding="utf-8"))
    c3pa, schema = open_c3pa(args.c3pa)
    say(f"OPP-115: {len(opp_clf)} classifier rows, {len(opp_ext)} extraction rows")
    say(f"C3PA:    {len(c3pa)} units")
    if schema is not None:
        assert schema == CATEGORIES, "label_schema.json differs from the category list in this script"
    for r in opp_clf:
        assert set(r["labels"]) <= set(CATEGORIES), f"unknown OPP-115 label in {r['policy_id']}"
    for r in c3pa:
        assert set(r["labels"]) <= set(CATEGORIES), f"unknown C3PA label in {r['unit_id']}"
        assert r["label_mask"] == r["label_mask"][:len(CATEGORIES)] and len(r["label_mask"]) == len(CATEGORIES)

    dom_of = opp_domains(args.opp_root)
    if not dom_of and args.opp_docs:
        dom_of = docs_domains(args.opp_docs)
    if not dom_of:
        say("WARNING: no --opp-root or --opp-docs given, so OPP-115 website domains are unknown. Companies present in both "
            "datasets cannot be kept together and cross-source leakage by company is NOT prevented.")
    else:
        say(f"OPP-115 website domains found for {len(dom_of)} policies")

    # ---------------- 1. drop C3PA text that is also in OPP-115 ----------------
    opp_keys = {text_key(r["text"]) for r in opp_clf}
    opp_sh = set()
    for r in opp_clf:
        opp_sh |= shingles(r["text"])
    dropped = []
    kept_c3pa = []
    for r in c3pa:
        k = text_key(r["text"])
        if k in opp_keys:
            dropped.append((r["unit_id"], "exact duplicate of an OPP-115 segment", r["text"][:200]))
            continue
        sh = shingles(r["text"])
        if sh and sum(h in opp_sh for h in sh) / len(sh) >= args.near_dup:
            dropped.append((r["unit_id"], f"near duplicate of OPP-115 text (>= {args.near_dup:.0%} shared phrases)",
                            r["text"][:200]))
            continue
        kept_c3pa.append(r)
    say(f"\n[dedup] C3PA units removed because the text is in OPP-115: {len(dropped)} "
        f"({Counter(d[1].split(' (')[0] for d in dropped)})")
    with open(out / "dropped_c3pa_units.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_id", "reason", "text"])
        w.writerows(dropped)

    # ---------------- 2. groups and splits ----------------
    def opp_group(policy_id):
        d = dom_of.get(policy_id)
        return f"dom:{d}" if d else f"opp115:{policy_id}"

    def c3pa_group(gid):
        return gid if gid.startswith("c3pa:") else f"dom:{base_domain(gid)}"

    # split that OPP-115 already assigned to each policy / company
    opp_policy_split = {r["policy_id"]: r["split"] for r in opp_clf}
    group_opp_splits = defaultdict(set)
    for pid, sp in opp_policy_split.items():
        group_opp_splits[opp_group(pid)].add(sp)
    order = {"test": 0, "validation": 1, "train": 2}
    inherited = {}
    n_conflict = 0
    for g, sps in group_opp_splits.items():
        if len(sps) > 1:
            n_conflict += 1  # OPP-115 itself has one company in several splits; be conservative
        inherited[g] = min(sps, key=order.get)
    if n_conflict:
        say(f"[split] NOTE: {n_conflict} OPP-115 companies already sit in more than one OPP-115 split")

    c3pa_units_per_group = Counter(c3pa_group(r["group_id"]) for r in kept_c3pa)
    fixed = {g: inherited[g] for g in c3pa_units_per_group if g in inherited}
    free = sorted(g for g in c3pa_units_per_group if g not in inherited)
    rng = random.Random(args.seed)
    rng.shuffle(free)
    total_free = sum(c3pa_units_per_group[g] for g in free)
    share = dict(zip(SPLITS, args.split))
    have = Counter()
    assign = dict(fixed)
    for g, sp in fixed.items():
        pass  # inherited units are not counted toward the random targets
    for g in free:
        # give the company to the split furthest below its target share
        sp = max(SPLITS, key=lambda s: share[s] * total_free - have[s])
        assign[g] = sp
        have[sp] += c3pa_units_per_group[g]
    say(f"[split] C3PA companies inheriting an OPP-115 split: {len(fixed)} "
        f"({sum(c3pa_units_per_group[g] for g in fixed)} units); assigned at random: {len(free)} "
        f"({total_free} units)")

    # ---------------- 3. build unified rows ----------------
    clf, ext = [], []
    for r in opp_clf:
        pid = r["policy_id"]
        clf.append(dict(
            id=f"opp115:{pid}#{r['segment_id']:04d}", source="opp115", doc_id=f"opp115:{pid}",
            group_id=opp_group(pid), split=r["split"], text=r["text"], labels=r["labels"],
            label_vec=multi_hot(r["labels"]), label_mask=[1] * len(CATEGORIES),
            label_fractions=r["label_fractions"], n_annotators=3, weight=1.0))
    for r in kept_c3pa:
        g = c3pa_group(r["group_id"])
        mask = ([1 if c in r["labels"] else 0 for c in CATEGORIES] if args.c3pa_mask == "positive"
                else list(r["label_mask"]))
        clf.append(dict(
            id=r["unit_id"], source="c3pa", doc_id=r["doc_id"], group_id=g, split=assign[g],
            text=r["text"], labels=r["labels"], label_vec=multi_hot(r["labels"]), label_mask=mask,
            label_fractions=None, n_annotators=r["n_annotators"], weight=args.c3pa_weight))
    for r in opp_ext:
        pid = r["policy_id"]
        ext.append(dict(
            id=f"opp115:{pid}#{r['segment_id']:04d}", source="opp115", doc_id=f"opp115:{pid}",
            group_id=opp_group(pid), split=r["split"], text=r["text"], tokens=r["tokens"],
            offsets=r["offsets"], tags=r["tags"], spans=r["spans"]))

    with open(out / "combined_classifier.jsonl", "w", encoding="utf-8") as f:
        for r in clf:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out / "combined_extraction.jsonl", "w", encoding="utf-8") as f:
        for r in ext:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out / "split_groups.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group_id", "source", "split", "rows"])
        cnt = Counter((r["group_id"], r["source"], r["split"]) for r in clf)
        for (g, s, sp), n in sorted(cnt.items()):
            w.writerow([g, s, sp, n])

    # ---------------- summary ----------------
    say("\nROWS PER SOURCE AND SPLIT")
    tab = Counter((r["source"], r["split"]) for r in clf)
    for s in ("opp115", "c3pa"):
        say(f"  {s:7s} " + "  ".join(f"{sp}={tab[(s, sp)]}" for sp in SPLITS) + f"  total={sum(tab[(s, sp)] for sp in SPLITS)}")
    say("\nCATEGORY COUNTS (rows with the label) BY SPLIT")
    for c in CATEGORIES:
        row = {sp: sum(1 for r in clf if r["split"] == sp and c in r["labels"]) for sp in SPLITS}
        srcs = {s: sum(1 for r in clf if r["source"] == s and c in r["labels"]) for s in ("opp115", "c3pa")}
        say(f"  {c:38s} train={row['train']:6d} val={row['validation']:5d} test={row['test']:5d}"
            f"   | opp115={srcs['opp115']:5d} c3pa={srcs['c3pa']:5d}")

    # ---------------- checks ----------------
    ck = Checks()
    ck.add("row counts: OPP-115 rows equal the input", sum(1 for r in clf if r["source"] == "opp115") == len(opp_clf))
    ck.add("row counts: C3PA rows == input minus removed duplicates",
           sum(1 for r in clf if r["source"] == "c3pa") == len(c3pa) - len(dropped),
           f"{sum(1 for r in clf if r['source'] == 'c3pa')} == {len(c3pa)} - {len(dropped)}")
    ck.add("ids are unique", len({r["id"] for r in clf}) == len(clf))
    ck.add("OPP-115 rows kept their original split",
           all(r["split"] == opp_policy_split[r["doc_id"].split(":", 1)[1]] for r in clf if r["source"] == "opp115"))
    ck.add("every row has a valid split", all(r["split"] in SPLITS for r in clf))
    ck.add("label vectors match label names and have 10 entries",
           all(r["label_vec"] == multi_hot(r["labels"]) and len(r["label_mask"]) == len(CATEGORIES) for r in clf))
    ck.add("every row has at least one label", all(r["labels"] for r in clf))
    ck.add("mask: OPP-115 rows supervise all 10 categories",
           all(all(m == 1 for m in r["label_mask"]) for r in clf if r["source"] == "opp115"))
    ck.add("mask: every labelled category is supervised (mask=1)",
           all(r["label_mask"][CAT_INDEX[l]] == 1 for r in clf for l in r["labels"]))
    if args.c3pa_mask == "positive":
        ck.add("mask: C3PA rows supervise only their positive labels",
               all(sum(r["label_mask"]) == len(r["labels"]) for r in clf if r["source"] == "c3pa"))
    else:
        cov = {i for r in c3pa for i, m in enumerate(r["label_mask"]) if m}
        ck.add("mask: C3PA rows keep the C3PA-covered categories",
               all({i for i, m in enumerate(r["label_mask"]) if m} == cov for r in clf if r["source"] == "c3pa"))

    # groups: a company that has any C3PA row must sit in exactly one split
    g_splits, g_src = defaultdict(set), defaultdict(set)
    for r in clf:
        g_splits[r["group_id"]].add(r["split"])
        g_src[r["group_id"]].add(r["source"])
    bad_c3pa = [g for g, s in g_splits.items() if "c3pa" in g_src[g] and len(s) > 1]
    ck.add("split: every company with C3PA data is in exactly one split", not bad_c3pa,
           f"{len(bad_c3pa)} violations {bad_c3pa[:3]}")
    bad_opp = [g for g, s in g_splits.items() if g_src[g] == {"opp115"} and len(s) > 1]
    ck.add("split: OPP-115-only companies in more than one split (inherited from OPP-115)", not bad_opp,
           f"{len(bad_opp)} companies", warn=True)
    both = [g for g in g_src if g_src[g] == {"opp115", "c3pa"}]
    same = all(len(g_splits[g]) == 1 for g in both)
    ck.add("split: companies present in both sources are in one split", same,
           f"{len(both)} shared companies")

    # duplicate text must not cross splits
    key_splits, key_src = defaultdict(set), defaultdict(set)
    for r in clf:
        k = text_key(r["text"])
        key_splits[k].add(r["split"])
        key_src[k].add(r["source"])
    cross = [k for k, s in key_splits.items() if len(s) > 1]
    cross_c3pa = [k for k in cross if "c3pa" in key_src[k]]
    ck.add("no text involving C3PA appears in more than one split", not cross_c3pa, f"{len(cross_c3pa)} texts")
    ck.add("no text is shared between OPP-115 and C3PA",
           not any(key_src[k] == {"opp115", "c3pa"} for k in key_src))
    ck.add("text repeated across splits inside OPP-115 itself (inherited)", not [k for k in cross if k not in set(cross_c3pa)],
           f"{len(cross) - len(cross_c3pa)} texts", warn=True)

    # category counts recomputed from the source files
    exp = Counter(l for r in opp_clf for l in r["labels"])
    exp.update(l for r in kept_c3pa for l in r["labels"])
    got = Counter(l for r in clf for l in r["labels"])
    ck.add("category totals == OPP-115 input + kept C3PA input", exp == got)

    # extraction file
    ck.add("extraction: rows are the OPP-115 rows (C3PA has no span tags)",
           len(ext) == len(opp_ext) and all(r["source"] == "opp115" for r in ext))
    ck.add("extraction: tokens, offsets and tags have equal lengths",
           all(len(r["tokens"]) == len(r["tags"]) == len(r["offsets"]) for r in ext))
    clf_split = {r["id"]: r["split"] for r in clf}
    ck.add("extraction: each row has the same split as the classifier row",
           all(clf_split.get(r["id"]) == r["split"] for r in ext))
    n_span = sum(len(r["spans"]) for r in ext)
    ck.add("extraction: span count unchanged", n_span == sum(len(r["spans"]) for r in opp_ext), str(n_span))

    say("\nCHECKS")
    for line in ck.lines():
        say(line)
    say("ALL CHECKS PASSED" if ck.ok else "SOME CHECKS FAILED")

    decisions = dict(
        c3pa_mask=args.c3pa_mask, c3pa_weight=args.c3pa_weight, near_duplicate_threshold=args.near_dup,
        shingle_words=SHINGLE, seed=args.seed, c3pa_split_targets=list(args.split),
        split_rule="OPP-115 keeps its own split; C3PA is split by company; a C3PA company that is also an "
                   "OPP-115 website inherits that website's split; other companies are assigned at random",
        dedup_rule="C3PA units whose text equals an OPP-115 segment, or shares >= near_dup of its 8-word "
                   "phrases with OPP-115, are removed (OPP-115 is kept because its labels are majority-voted)",
        categories=CATEGORIES)
    (out / "decisions.json").write_text(json.dumps(decisions, indent=2))
    (out / "combine_report.txt").write_text("\n".join(log), encoding="utf-8")
    sys.exit(0 if ck.ok else 1)


if __name__ == "__main__":
    main()
