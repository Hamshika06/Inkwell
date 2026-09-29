#!/usr/bin/env python3
"""
OPP-115 preprocessing (single, standalone script).

Follows the logic of opp115_preprocess.py (v1): with the default settings it produces the
same rows, labels, BIO tags and train/validation/test split as v1, and it also writes the
report files and the shared row format used for C3PA (same columns as
preprocessing/reports/c3pa/ and data/interim/c3pa.jsonl).

Usage:
    python opp115_preprocess_final.py --root OPP-115_v1_0.zip --out output_final
    python opp115_preprocess_final.py --root OPP-115 --threshold 0.75 --no-majority drop
    python opp115_preprocess_final.py --root OPP-115 --dedup        # also remove duplicate segments

Steps
    1  load sanitized_policies/, split on |||, number segments from 0
    2  key every policy by FILENAME prefix (the policy-id column in the CSVs is ignored)
    3  load annotations/ (all three annotators)
    4  verify each span against the RAW segment; repair by text search or drop
    5  remove known-bad spans (documentation/errant_span_indexes/)
    6  category labels by majority vote (>= 2 of 3 annotators) + fraction of annotators
    7  segments with no majority category: dropped, kept unlabelled, or labelled "Other"
    8  compare the consolidation thresholds, use --threshold for the spans
    9  clean text (<br> -> space, other tags removed, whitespace collapsed) AFTER step 4 and
       remap spans onto the cleaned text
    10 optional: remove duplicate segments (--dedup)
    11 split by policy into train / validation / test
    12 write the outputs, then run the checks (exit code 1 if any check fails)

Outputs (in --out)
    opp115.jsonl             shared row format (same keys, same order as c3pa.jsonl)
    classifier_data.jsonl    segment -> categories (with split and label_fractions)
    extraction_data.jsonl    words -> BIO tags (PII_TYPE, THIRD_PARTY, PURPOSE, RETENTION)
    funnel.csv               units and label counts after each step
    dropped_units.csv        every dropped segment with the reason
    opp115_docs.csv          one row per policy: title, url, domain, n_units, group_id, split
    threshold_comparison.csv, span_report.csv
    train/validation/test_policies.txt, decisions.json, label_schema.json, summary.txt
"""
import argparse
import bisect
import csv
import json
import random
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ANN_COLS = ["ann_id", "batch", "annotator", "policy_col", "segment_id",
            "category", "attrs", "url", "html"]
THRESHOLDS = ["0.5", "0.75", "1.0"]
EXTRACTION_ATTRS = {  # attribute name in the JSON -> BIO tag suffix
    "Personal Information Type": "PII_TYPE",
    "Third Party Entity": "THIRD_PARTY",
    "Purpose": "PURPOSE",
    "Retention Period": "RETENTION",
}
CATEGORIES = ["First Party Collection/Use", "Third Party Sharing/Collection", "User Choice/Control",
              "Data Security", "International and Specific Audiences", "User Access, Edit and Deletion",
              "Policy Change", "Data Retention", "Do Not Track", "Other"]
CAT_INDEX = {c: i for i, c in enumerate(CATEGORIES)}
# key order of a row in data/interim/c3pa.jsonl
SHARED_KEYS = ["source", "doc_id", "group_id", "unit_id", "text", "labels", "label_mask", "spans",
               "subset", "n_words", "n_annotators", "n_copies", "orig_labels"]
DOCS_COLUMNS = ["doc_id", "uid", "subset", "title", "site_name", "url", "domain", "n_units", "group_id"]
SPLITS = ("train", "validation", "test")
TAG_RE = re.compile(r"<[^>]*>")
BR_RE = re.compile(r"<br\s*/?>", re.I)
TOKEN_RE = re.compile(r"\w+|[^\w\s]")


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def resolve_root(path):
    p = Path(path)
    if p.suffix.lower() == ".zip":
        out = Path(tempfile.mkdtemp(prefix="opp115_"))
        wanted = ("/annotations/", "/consolidation/", "/sanitized_policies/", "/documentation/")
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.startswith("__MACOSX"):
                    continue
                if any(w in name for w in wanted):
                    z.extract(name, out)
        found = list(out.glob("*/annotations"))
        if not found:
            sys.exit("Could not find annotations/ inside the zip.")
        return found[0].parent
    if (p / "annotations").exists():
        return p
    if (p / "OPP-115" / "annotations").exists():
        return p / "OPP-115"
    sys.exit(f"Could not find annotations/ under {p}")


def prefix_of(path):
    return Path(path).name.split("_")[0]


def text_key(s):
    """Duplicate-detection key: lowercase letters and digits only (same as the C3PA script)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_domain(url):
    """'https://www.Example.com/privacy' or 'example.com/x' -> 'example.com'."""
    url = (url or "").strip()
    if not url or url.lower() == "nan":
        return ""
    if not url.startswith("http"):
        url = "http://" + url
    d = urlparse(url).netloc.lower().split(":")[0]
    return d[4:] if d.startswith("www.") else d


def load_policies(root):
    """Steps 1-2: {prefix: [raw segment, ...]}, segments numbered from 0."""
    policies = {}
    for f in sorted((root / "sanitized_policies").iterdir()):
        if not f.is_file():
            continue
        pre = prefix_of(f)
        assert pre not in policies, f"duplicate filename prefix {pre}"
        # decode bytes directly so newlines are not translated (offsets must stay exact)
        policies[pre] = f.read_bytes().decode("utf-8", errors="replace").split("|||")
    return policies


def load_csv_dir(folder):
    """Step 3: annotation-style CSVs (annotations/ and consolidation/), keyed by filename prefix."""
    dfs = []
    for f in sorted(Path(folder).rglob("*.csv")):
        df = pd.read_csv(f, header=None, names=ANN_COLS, dtype=str, encoding="utf-8",
                         encoding_errors="replace", keep_default_na=False)
        df["prefix"] = prefix_of(f)
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df["segment_id"] = pd.to_numeric(df["segment_id"], errors="coerce")
    df = df.dropna(subset=["segment_id"]).copy()
    df["segment_id"] = df["segment_id"].astype(int)
    return df


def load_errant(root):
    """Known-bad spans as a set of (annotation_id, attribute_name).

    A line looks like `20143,1_Third Party Entity`: annotation id, then `<n>_<attribute>`.
    The number is NOT the segment id (it agrees with it for only a handful of lines), so it
    is ignored and the pair (annotation id, attribute) is used.
    """
    errant = set()
    for f in sorted((root / "documentation" / "errant_span_indexes").glob("*.csv")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if "," not in line:
                continue
            a, b = line.strip().split(",", 1)
            errant.add((a.strip(), re.sub(r"^\d+_", "", b.strip())))
    return errant


def load_doc_meta(root, policies):
    """Per-policy title, url and domain from documentation/ (matched by filename prefix)."""
    meta_dir = root / "documentation"
    w = pd.read_csv(meta_dir / "websites_opp115.csv", dtype=str, encoding_errors="replace")
    w = w.drop_duplicates("Policy UID").set_index("Policy UID")
    p = pd.read_csv(meta_dir / "policies_opp115.csv", dtype=str, encoding_errors="replace")
    p = p.drop_duplicates("Policy UID").set_index("Policy UID")
    file_domain = {}
    for f in (root / "sanitized_policies").iterdir():
        if f.is_file() and "_" in f.name:
            pre, rest = f.name.split("_", 1)
            file_domain[pre] = norm_domain(rest.rsplit(".", 1)[0])
    rows = {}
    for pre in policies:
        name = w["Site Human-Readable Name"].get(pre, "") if pre in w.index else ""
        site_url = w["Site URL"].get(pre, "") if pre in w.index else ""
        pol_url = p["Policy URL"].get(pre, "") if pre in p.index else ""
        name = "" if pd.isna(name) else str(name)
        url = "" if pd.isna(pol_url) else str(pol_url)
        if url and not url.startswith("http"):
            url = "http://" + url
        domain = (norm_domain(site_url if isinstance(site_url, str) else "") or norm_domain(url)
                  or file_domain.get(pre, ""))
        rows[pre] = dict(title=name, site_name=name, url=url, domain=domain)
    return rows


# --------------------------------------------------------------------------
# Steps 4 + 5: span verification
# --------------------------------------------------------------------------
def explode_attrs(df):
    """One row per attribute entry; has_span is True only for real highlighted spans."""
    rows = []
    for r in df.itertuples(index=False):
        try:
            attrs = json.loads(r.attrs)
        except Exception:
            continue
        if not isinstance(attrs, dict):
            continue
        for name, d in attrs.items():
            if not isinstance(d, dict):
                continue
            s, e, t = d.get("startIndexInSegment"), d.get("endIndexInSegment"), d.get("selectedText")
            has = (isinstance(t, str) and t.strip() not in ("", "null")
                   and isinstance(s, (int, float)) and isinstance(e, (int, float))
                   and int(s) >= 0 and int(e) > int(s))
            rows.append(dict(prefix=r.prefix, ann_id=r.ann_id, annotator=r.annotator,
                             segment_id=r.segment_id, category=r.category, attribute=name,
                             value=d.get("value"), has_span=has, text=t if has else None,
                             start0=int(s) if has else -1, end0=int(e) if has else -1))
    return pd.DataFrame(rows)


def verify_span(prefix, seg_id, text, s0, e0, policies):
    """Check a span on the RAW segment. Returns (status, start, end)."""
    segs = policies.get(prefix)
    if segs is None or seg_id >= len(segs):
        return "dropped", -1, -1
    seg = segs[seg_id]
    if seg[s0:e0] == text:
        return "ok", s0, e0
    occ = [m.start() for m in re.finditer(re.escape(text), seg)]
    if occ:
        s = min(occ, key=lambda x: abs(x - s0))  # nearest occurrence to the stated start
        return "fixed", s, s + len(text)
    return "dropped", -1, -1


def process_attrs(df, policies, errant):
    a = explode_attrs(df)
    a["errant"] = [(r.ann_id, r.attribute) in errant for r in a.itertuples()]
    res = [verify_span(r.prefix, r.segment_id, r.text, r.start0, r.end0, policies)
           if r.has_span else ("nospan", -1, -1) for r in a.itertuples()]
    a["status"] = [x[0] for x in res]
    a["start"] = [x[1] for x in res]
    a["end"] = [x[2] for x in res]
    a.loc[a.errant & a.has_span, "status"] = "errant"  # step 5 (overrides ok/fixed)
    return a


# --------------------------------------------------------------------------
# Step 9: cleaning with an offset map
# --------------------------------------------------------------------------
def clean_with_map(raw):
    """Clean a raw segment. Returns (clean_text, src) with src[i] = raw index of clean char i."""
    pieces, pos = [], 0
    for m in TAG_RE.finditer(raw):
        pieces += [(c, i) for i, c in enumerate(raw[pos:m.start()], start=pos)]
        if BR_RE.fullmatch(m.group()):
            pieces.append((" ", m.start()))
        pos = m.end()
    pieces += [(c, i) for i, c in enumerate(raw[pos:], start=pos)]
    out, src = [], []
    for ch, si in pieces:
        if ch.isspace():
            if not out or out[-1] == " ":
                continue
            out.append(" ")
            src.append(si)
        else:
            out.append(ch)
            src.append(si)
    while out and out[-1] == " ":
        out.pop()
        src.pop()
    return "".join(out), src


def remap_span(clean, src, s, e):
    """Map a raw-text span [s, e) onto the cleaned text; None if nothing is left."""
    cs, ce = bisect.bisect_left(src, s), bisect.bisect_left(src, e)
    while cs < ce and clean[cs] == " ":
        cs += 1
    while ce > cs and clean[ce - 1] == " ":
        ce -= 1
    return (cs, ce) if ce > cs else None


# --------------------------------------------------------------------------
# BIO tagging
# --------------------------------------------------------------------------
def bio_encode(text, spans):
    """spans: iterable of (char_start, char_end, attribute).

    Each span is snapped outward to whole tokens. Shorter spans get priority; a span that
    would overlap an already accepted one is rejected, so every kept span decodes back
    exactly. Returns (tokens, offsets, tags, accepted, rejected); accepted items are
    (tok_start, tok_end_exclusive, attribute, orig_start, orig_end); rejected items carry a
    conflict kind (same_type / other_type / no_tokens).
    """
    toks = [(m.group(), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
    owner = [None] * len(toks)
    accepted, rejected = [], []
    for s, e, attr in sorted(spans, key=lambda x: (x[1] - x[0], x[0], x[2])):
        idx = [i for i, (_, ts, te) in enumerate(toks) if ts < e and te > s]
        if not idx or any(owner[i] is not None for i in idx):
            owners = {accepted[owner[i]][2] for i in idx if owner[i] is not None}
            kind = "no_tokens" if not idx else "same_type" if owners <= {attr} else "other_type"
            rejected.append((s, e, attr, kind))
            continue
        for i in idx:
            owner[i] = len(accepted)
        accepted.append((idx[0], idx[-1] + 1, attr, s, e))
    accepted.sort()
    tags = ["O"] * len(toks)
    for ts, te, attr, _, _ in accepted:
        suf = EXTRACTION_ATTRS[attr]
        tags[ts] = "B-" + suf
        for i in range(ts + 1, te):
            tags[i] = "I-" + suf
    return [t[0] for t in toks], [(t[1], t[2]) for t in toks], tags, accepted, rejected


def bio_decode(tags):
    """BIO tags -> list of (tok_start, tok_end_exclusive, tag_suffix)."""
    out, cur = [], None
    for i, t in enumerate(tags):
        if t == "O":
            if cur:
                out.append(tuple(cur))
                cur = None
        elif t.startswith("B-") or cur is None or cur[2] != t[2:]:
            if cur:
                out.append(tuple(cur))
            cur = [i, i + 1, t[2:]]
        else:
            cur[1] = i + 1
    if cur:
        out.append(tuple(cur))
    return out


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
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


def independent_category_counts(ann_dir, kept_keys, no_majority):
    """Recount majority-vote categories with plain csv code (no shared code with the pipeline)."""
    voters = defaultdict(set)
    for f in sorted(Path(ann_dir).rglob("*.csv")):
        with open(f, encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) < 6:
                    continue
                voters[(prefix_of(f), int(row[4]), row[5])].add(row[2])
    per_seg = defaultdict(list)
    for (pre, seg, cat), who in voters.items():
        if len(who) >= 2:
            per_seg[(pre, seg)].append(cat)
    counts = Counter()
    for key in kept_keys:
        cats = per_seg.get(key, [])
        if not cats and no_majority == "other":
            cats = ["Other"]
        counts.update(cats)
    return counts


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="OPP-115 folder or zip")
    ap.add_argument("--out", default="output_final")
    ap.add_argument("--threshold", default="0.75", choices=THRESHOLDS, help="consolidation threshold for spans")
    ap.add_argument("--no-majority", default="drop", choices=["drop", "keep", "other"],
                    help="segments with no category chosen by 2 of 3 annotators: drop, keep with no labels, "
                         "or label 'Other'")
    ap.add_argument("--dedup", action="store_true", help="remove duplicate segments (off by default, as in v1)")
    ap.add_argument("--conflict", default="drop", choices=["drop", "union"],
                    help="with --dedup: same text with different labels: drop all copies, or merge labels")
    ap.add_argument("--only-segments-with-spans", action="store_true",
                    help="extraction_data: skip segments that have no spans")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--split", type=float, nargs=3, default=(0.8, 0.1, 0.1), metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--schema", default=None, help="existing label_schema.json to verify the categories against")
    ap.add_argument("--eda-tables", default=None, help="EDA tables folder for an information-only comparison")
    args = ap.parse_args()

    root = resolve_root(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = []

    def say(msg=""):
        print(msg)
        log.append(str(msg))

    def header(title):
        say("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)

    funnel, dropped = [], []

    def log_step(step, df):
        row = {"step": step, "units": len(df), "files": df.pre.nunique()}
        if "labels" in df and len(df):
            row.update(df.labels.explode().value_counts().to_dict())
        funnel.append(row)
        say(f"  -> {step}: {len(df):,} units in {df.pre.nunique()} files")

    def log_drop(df, reason):
        if len(df):
            dropped.append(pd.DataFrame({"uid": "opp115/" + df.pre, "Text": df.text.str[:300], "reason": reason}))

    if args.schema and Path(args.schema).exists():
        assert json.loads(Path(args.schema).read_text())["categories"] == CATEGORIES, \
            "label_schema.json differs from CATEGORIES"
        say(f"label_schema.json ({args.schema}) found and matches.")
    (out / "label_schema.json").write_text(json.dumps({"version": 1, "categories": CATEGORIES}, indent=2))
    say(f"OPP-115 root: {root}")

    # ---------------- steps 1-3 ----------------
    header("STEP 1  LOAD")
    policies = load_policies(root)
    ann = load_csv_dir(root / "annotations")
    n_ann = ann.groupby("prefix").annotator.nunique()
    assert set(ann.prefix) <= set(policies), "annotation file without a policy text"
    assert (n_ann == 3).all(), "majority vote assumes exactly 3 annotators per policy"
    errant = load_errant(root)
    say(f"{len(policies)} policies, {sum(map(len, policies.values()))} segments, {len(ann)} annotation rows, "
        f"{len(errant)} known-bad span entries")

    # ---------------- steps 4-5 on the raw annotations ----------------
    ann_attrs = process_attrs(ann, policies, errant)
    say(f"Raw annotation spans: {ann_attrs[ann_attrs.has_span].status.value_counts().to_dict()}")
    (ann_attrs[ann_attrs.has_span].groupby(["attribute", "status"]).size().unstack(fill_value=0)
     .reset_index().to_csv(out / "span_report.csv", index=False))

    # ---------------- step 6: majority vote ----------------
    header("STEP 2  MAJORITY VOTE")
    votes = (ann.drop_duplicates(["prefix", "segment_id", "annotator", "category"])
             .groupby(["prefix", "segment_id", "category"]).size().rename("n").reset_index())
    votes["frac"] = votes.n / votes.prefix.map(n_ann)
    labels, fracs = defaultdict(list), defaultdict(dict)
    for r in votes.itertuples():
        fracs[(r.prefix, r.segment_id)][r.category] = round(r.frac, 4)
        if r.n >= 2:
            labels[(r.prefix, r.segment_id)].append(r.category)
    unknown = set(votes.category) - set(CATEGORIES)
    assert not unknown, f"categories not in the schema: {unknown}"

    # ---------------- step 9 (after step 4): clean every segment ----------------
    rows = []
    for pre, segs in policies.items():
        for i, raw in enumerate(segs):
            clean, src = clean_with_map(raw)
            rows.append(dict(pre=pre, seg=i, text=clean, src=src,
                             labels=sorted(labels.get((pre, i), [])), fracs=fracs.get((pre, i), {})))
    units = pd.DataFrame(rows)
    n_all = len(units)
    log_step("all segments", units)

    empty = units[units.text.str.len() == 0]
    log_drop(empty, "empty text after cleaning")
    units = units.drop(empty.index).reset_index(drop=True)

    # ---------------- step 7 ----------------
    none = units.labels.str.len() == 0
    say(f"Segments with no majority category: {int(none.sum())} (expected 63)")
    if args.no_majority == "drop":
        log_drop(units[none], "no category chosen by 2 of 3 annotators")
        units = units[~none].reset_index(drop=True)
        say("No-majority segments dropped.")
    elif args.no_majority == "other":
        units.loc[none, "labels"] = units.loc[none, "labels"].map(lambda _: ["Other"])
        say("No-majority segments labelled 'Other'.")
    else:
        say("No-majority segments kept without labels.")
    log_step("after majority vote", units)

    # ---------------- duplicates (reported always, removed only with --dedup) ----------------
    header("STEP 3  DUPLICATES")
    units["text_key"] = units.text.map(text_key)
    g = units.groupby("text_key")
    units["n_copies"] = g.pre.transform("size")
    lk = units.labels.map(tuple)
    conflict = lk.groupby(units.text_key).transform("nunique") > 1
    say(f"Distinct texts with >1 copy: {(g.size() > 1).sum():,} ({(units.n_copies > 1).sum():,} units)")
    say(f"...with conflicting label sets: {units.loc[conflict, 'text_key'].nunique():,} texts ({conflict.sum():,} units)")
    if args.dedup:
        if args.conflict == "drop":
            log_drop(units[conflict], "same text, conflicting labels across policies")
            units = units[~conflict].copy()
        else:
            merged = units[conflict].groupby("text_key").labels.agg(
                lambda s: sorted({l for ls in s for l in ls}))
            units["labels"] = [merged[k] if c else ls for k, c, ls in zip(units.text_key, conflict, units.labels)]
        dup = units.duplicated("text_key", keep="first")
        log_drop(units[dup], "duplicate text (first copy kept)")
        units = units[~dup].reset_index(drop=True)
        say(f"Removed {int(dup.sum()):,} duplicate copies")
        log_step("after dedup", units)
    else:
        say("Duplicates kept (use --dedup to remove them).")

    # ---------------- policy metadata and groups ----------------
    header("STEP 4  POLICY METADATA AND GROUPS")
    meta = load_doc_meta(root, policies)
    docs = pd.DataFrame([{"doc_id": f"opp115:{p}", "uid": f"opp115/{p}", "subset": "opp115", **meta[p]}
                         for p in policies])
    docs["n_units"] = docs.uid.map(("opp115/" + units.pre).value_counts()).fillna(0).astype(int)
    docs["group_id"] = docs.apply(lambda r: r.domain if r.domain else r.doc_id, axis=1)
    say(f"Policies with a domain: {(docs.domain != '').mean() * 100:.1f}%")
    shared = docs[docs.domain != ""].groupby("domain").doc_id.nunique()
    say(f"Domains with more than one policy (must share a split): {(shared > 1).sum()}")
    say(f"Policies with 0 units left: {(docs.n_units == 0).sum()}")
    group_of = dict(zip(docs.uid.str.split("/").str[1], docs.group_id))
    units["group_id"] = units.pre.map(group_of)

    # ---------------- step 8: thresholds and spans ----------------
    header("STEP 5  SPANS (consolidation)")
    cons, cmp_rows = {}, []
    for t in THRESHOLDS:
        folder = next(p for p in (root / "consolidation").iterdir() if p.is_dir() and f"threshold-{t}-" in p.name)
        rows_t = load_csv_dir(folder)
        a = process_attrs(rows_t, policies, errant)
        cons[t] = a
        sp = a[a.has_span]
        good = sp[sp.status.isin(["ok", "fixed"])]
        cmp_rows.append(dict(threshold=t, rows=len(rows_t), attr_entries=len(a), with_span=len(sp),
                             span_ok=int((sp.status == "ok").sum()), span_fixed=int((sp.status == "fixed").sum()),
                             span_dropped=int((sp.status == "dropped").sum()),
                             span_errant=int((sp.status == "errant").sum()),
                             segments_with_spans=good.drop_duplicates(["prefix", "segment_id"]).shape[0]))
    cmp_df = pd.DataFrame(cmp_rows)
    cmp_df.to_csv(out / "threshold_comparison.csv", index=False)
    say(cmp_df.to_string(index=False))
    say(f"chosen threshold: {args.threshold}")

    ca = cons[args.threshold]
    ca = ca[ca.has_span & ca.status.isin(["ok", "fixed"]) & ca.attribute.isin(EXTRACTION_ATTRS)]
    index = {(r.pre, r.seg): r for r in units.itertuples()}
    span_lookup, lost = defaultdict(set), 0
    for r in ca.itertuples():
        u = index.get((r.prefix, r.segment_id))
        if u is None:
            continue
        m = remap_span(u.text, u.src, r.start, r.end)
        if m:
            span_lookup[(r.prefix, r.segment_id)].add((m[0], m[1], r.attribute, str(r.value)))
        else:
            lost += 1
    say(f"Spans lost while cleaning: {lost}")

    # ---------------- step 11: split by policy ----------------
    pols = sorted(units.pre.unique())
    random.Random(args.seed).shuffle(pols)
    n = len(pols)
    n_tr, n_va = int(args.split[0] * n), int(args.split[1] * n)
    split_of = {p: "train" if i < n_tr else "validation" if i < n_tr + n_va else "test" for i, p in enumerate(pols)}
    for s in SPLITS:
        (out / f"{s}_policies.txt").write_text("\n".join(p for p in pols if split_of[p] == s))
    units["split"] = units.pre.map(split_of)
    docs["split"] = docs.uid.str.split("/").str[1].map(split_of).fillna("")
    say(f"\nSegments per split: {units.groupby('split').size().to_dict()}; policies per split: {Counter(split_of.values())}")

    # ---------------- step 12: build and write the outputs ----------------
    header("STEP 6  BUILD AND VALIDATE")
    units["n_words"] = units.text.str.split().str.len()
    shared_rows, clf_rows, ext_rows = [], [], []
    n_rej = Counter()
    for r in units.itertuples():
        doc_id = f"opp115:{r.pre}"
        spans4 = sorted(span_lookup.get((r.pre, r.seg), set()))
        ordered = sorted(r.labels, key=CAT_INDEX.get)
        shared_rows.append(dict(
            source="opp115", doc_id=doc_id, group_id=r.group_id, unit_id=f"{doc_id}#{r.seg:04d}", text=r.text,
            labels=ordered, label_mask=[1] * len(CATEGORIES),
            spans=[dict(type=a, value=v, start=s, end=e, text=r.text[s:e]) for s, e, a, v in spans4],
            subset="opp115", n_words=int(r.n_words), n_annotators=int(n_ann[r.pre]),
            n_copies=int(r.n_copies), orig_labels=list(ordered)))
        clf_rows.append(dict(policy_id=r.pre, segment_id=int(r.seg), split=r.split, text=r.text,
                             labels=list(r.labels), label_fractions=r.fracs))
        uniq = {(s, e, a) for s, e, a, _ in spans4}
        if args.only_segments_with_spans and not uniq:
            continue
        toks, offs, tags, acc, rej = bio_encode(r.text, uniq)
        n_rej.update(x[3] for x in rej)
        sp_out = [dict(type=attr, tok_start=ts, tok_end=te, start=offs[ts][0], end=offs[te - 1][1],
                       text=r.text[offs[ts][0]:offs[te - 1][1]], original_text=r.text[os_:oe])
                  for ts, te, attr, os_, oe in acc]
        ext_rows.append(dict(policy_id=r.pre, segment_id=int(r.seg), split=r.split, text=r.text,
                             tokens=toks, offsets=offs, tags=tags, spans=sp_out))

    for name, recs in (("opp115.jsonl", shared_rows), ("classifier_data.jsonl", clf_rows),
                       ("extraction_data.jsonl", ext_rows)):
        with open(out / name, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    dropped_df = pd.concat(dropped, ignore_index=True) if dropped else pd.DataFrame(columns=["uid", "Text", "reason"])
    dropped_df.to_csv(out / "dropped_units.csv", index=False)
    pd.DataFrame(funnel).fillna(0).to_csv(out / "funnel.csv", index=False)
    docs[DOCS_COLUMNS + ["split"]].to_csv(out / "opp115_docs.csv", index=False)

    say(f"\nFinal: {len(shared_rows):,} units from {units.pre.nunique()} policies, {units.group_id.nunique()} groups")
    say("Units per split: " + str(units.split.value_counts().to_dict()))
    say("Category counts:\n" + units.labels.explode().value_counts().to_string())
    say(f"Spans in opp115.jsonl: {sum(len(r['spans']) for r in shared_rows):,}; extraction rows: {len(ext_rows):,}; "
        f"BIO spans kept: {sum(len(r['spans']) for r in ext_rows):,}; rejected: {dict(n_rej)} "
        "(same_type = overlaps a span of the same attribute, mostly duplicate highlights; other_type = "
        "overlaps a span of a different attribute, which BIO cannot represent)")
    if len(dropped_df):
        say("Dropped by reason:\n" + dropped_df.reason.value_counts().to_string())

    # ---------------- checks ----------------
    ck = Checks()
    ids = [r["unit_id"] for r in shared_rows]
    ck.add("shared rows: unit_id is unique", len(set(ids)) == len(ids))
    ck.add("shared rows: keys and key order equal the C3PA row format",
           all(list(r.keys()) == SHARED_KEYS for r in shared_rows))
    ck.add("shared rows: text is non-empty and free of literal \\n",
           all(r["text"] and "\\n" not in r["text"] for r in shared_rows))
    ck.add("shared rows: labels are in the schema, mask has 10 ones",
           all(set(r["labels"]) <= set(CATEGORIES) and r["label_mask"] == [1] * 10 for r in shared_rows))
    if args.no_majority == "keep":
        ck.add("shared rows: unlabelled rows only because of --no-majority keep", True,
               f"{sum(1 for r in shared_rows if not r['labels'])} rows")
    else:
        ck.add("shared rows: every row has at least one label", all(r["labels"] for r in shared_rows))
    ck.add("shared rows: group_id is set", all(r["group_id"] for r in shared_rows))
    ck.add("shared rows: span offsets cut the row text back out",
           all(r["text"][s["start"]:s["end"]] == s["text"] for r in shared_rows for s in r["spans"]))
    if args.dedup:
        ck.add("no duplicate text remains", units.text_key.is_unique)
    ck.add("row counts: opp115.jsonl == classifier_data.jsonl", len(shared_rows) == len(clf_rows),
           f"{len(shared_rows)} vs {len(clf_rows)}")
    ck.add("row counts: extraction_data.jsonl == classifier_data.jsonl (unless span-only filter)",
           args.only_segments_with_spans or len(ext_rows) == len(clf_rows), f"{len(ext_rows)} vs {len(clf_rows)}")
    ck.add("row counts: funnel last step == rows written", funnel[-1]["units"] == len(shared_rows))
    ck.add("row counts: all segments - dropped == rows written",
           n_all - len(dropped_df) == len(shared_rows), f"{n_all} - {len(dropped_df)} = {n_all - len(dropped_df)}")
    ck.add("reports: docs csv has the C3PA columns first", list(docs.columns[:len(DOCS_COLUMNS)]) == DOCS_COLUMNS)
    ck.add("reports: dropped csv columns are uid, Text, reason", list(dropped_df.columns) == ["uid", "Text", "reason"])
    ck.add("reports: funnel csv starts with step, units, files",
           list(pd.read_csv(out / "funnel.csv").columns[:3]) == ["step", "units", "files"])

    by_policy, by_group = defaultdict(set), defaultdict(set)
    for r in clf_rows:
        by_policy[r["policy_id"]].add(r["split"])
    for r in ext_rows:
        by_policy[r["policy_id"]].add(r["split"])
    for r in units.itertuples():
        by_group[r.group_id].add(r.split)
    ck.add("split: every policy is in exactly one split (both output files)",
           all(len(s) == 1 for s in by_policy.values()))
    ck.add("split: every company (group_id) is in exactly one split", all(len(s) == 1 for s in by_group.values()),
           f"{sum(1 for s in by_group.values() if len(s) > 1)} violations")
    lists = {s: set((out / f"{s}_policies.txt").read_text().split()) for s in SPLITS}
    ck.add("split: policy lists are disjoint, match the data and cover all policies with units",
           not (lists["train"] & lists["validation"] or lists["train"] & lists["test"]
                or lists["validation"] & lists["test"])
           and set().union(*lists.values()) == set(units.pre)
           and all(split_of[p] == s for s in SPLITS for p in lists[s]))
    key_splits = defaultdict(set)
    for r in units.itertuples():
        key_splits[r.text_key].add(r.split)
    n_cross = sum(1 for s in key_splits.values() if len(s) > 1)
    ck.add("split: text repeated across splits" + ("" if args.dedup else " (duplicates were kept; use --dedup)"),
           n_cross == 0, f"{n_cross} texts", warn=not args.dedup)

    got = Counter(l for r in shared_rows for l in r["labels"])
    if not args.dedup or args.conflict == "drop":  # merged labels differ from the raw votes on purpose
        exp = independent_category_counts(root / "annotations", list(zip(units.pre, units.seg)), args.no_majority)
        ck.add("labels: category counts == independent recount from annotations/ for the kept segments", got == exp,
               "" if got == exp else f"diff: { {k: (got.get(k), exp.get(k)) for k in set(got) | set(exp) if got.get(k) != exp.get(k)} }")
    ck.add("labels: label_fractions agree with the majority labels (>= 2/3)",
           args.no_majority != "drop" or all(all(r['label_fractions'].get(c, 0) >= 2 / 3 - 1e-3 for c in r['labels'])
                                             for r in clf_rows))

    bad = 0
    fidelity = 0
    n_spans = 0
    for r in ext_rows:
        if not (len(r["tokens"]) == len(r["tags"]) == len(r["offsets"])):
            bad += 1
            continue
        want = sorted((s["tok_start"], s["tok_end"], EXTRACTION_ATTRS[s["type"]]) for s in r["spans"])
        dec = bio_decode(r["tags"])
        ok = sorted(dec) == want
        for (a, b, _), s in zip(dec, sorted(r["spans"], key=lambda x: (x["tok_start"], x["tok_end"]))):
            n_spans += 1
            decoded = r["text"][r["offsets"][a][0]:r["offsets"][b - 1][1]]
            ok = ok and decoded == s["text"]
            fidelity += decoded == s["original_text"]
        bad += not ok
    ck.add("extraction: BIO tags decode back to the saved spans and their text", bad == 0,
           f"{n_spans} spans, {bad} bad rows")
    ck.add("extraction: info -- decoded span text equals the originally highlighted text", True,
           f"{fidelity}/{n_spans} exact ({fidelity / max(n_spans, 1):.1%}); the rest differ only because spans are "
           "widened to whole tokens")

    eda_dir = Path(args.eda_tables) if args.eda_tables else None
    if eda_dir is None:
        here = Path(__file__).resolve().parent
        for cand in (here.parent / "eda" / "outputs" / "opp115" / "tables",
                     here.parent / "EDA_OPP115" / "output" / "tables"):
            if cand.exists():
                eda_dir = cand
                break
    if eda_dir and (eda_dir / "category_counts.csv").exists():
        eda = pd.read_csv(eda_dir / "category_counts.csv", index_col=0)["segments_majority"].to_dict()
        diff = {c: (eda.get(c, 0), got.get(c, 0)) for c in CATEGORIES if eda.get(c, 0) != got.get(c, 0)}
        ck.add("info: category counts vs the EDA", True, f"{diff}" if diff else "identical to the EDA")

    say("\nCHECKS")
    for line in ck.lines():
        say(line)
    say("ALL CHECKS PASSED" if ck.ok else "SOME CHECKS FAILED")

    (out / "decisions.json").write_text(json.dumps(dict(
        no_majority_policy=args.no_majority, consolidation_threshold=args.threshold,
        dedup=args.dedup, conflict_policy=args.conflict if args.dedup else None,
        extraction_attrs=EXTRACTION_ATTRS, keep_only_segments_with_spans=args.only_segments_with_spans,
        split=list(args.split), seed=args.seed, split_unit="policy (company-level checked via group_id)",
        majority_rule=">= 2 of 3 annotators; label_fractions saved in classifier_data.jsonl",
        span_repair="offsets checked on the raw segment; on mismatch search for the text (nearest), else drop",
        errant_spans="removed by (annotation id, attribute) from documentation/errant_span_indexes",
        bio_overlap_rule="spans snapped to whole tokens; shorter wins; overlapping spans rejected",
        cleaning="<br> -> space, other tags removed, whitespace collapsed, done after the span check",
        categories=CATEGORIES,
        skipped_folders=["original_policies", "pretty_print", "pretty_print_uniquified"]), indent=2))
    say("\nDONE")
    say(f"Data and reports: {out}")
    (out / "summary.txt").write_text("\n".join(log), encoding="utf-8")
    sys.exit(0 if ck.ok else 1)


if __name__ == "__main__":
    main()
