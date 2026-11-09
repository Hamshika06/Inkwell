"""Collapse PolicyIE into the five broad classes and clean it for fine-tuning.

Reads data/interim/policyie.jsonl (written by policyie_preprocess.py, already mapped from
PolicyIE practices to OPP-115's ten categories) and the raw PolicyIE annotations, and writes
five-class rows using the same table as OPP-115: configs/five_class_mapping.json.

Example:
    python preprocessing/policyie_to_five_class.py \
      --raw "../MSML641/PolicyIE/sanitized_split" \
      --out data/interim/policyie_five_class.jsonl

Steps, in order:
  1. Corrections. Hand-reviewed fixes in configs/policyie_mapping.json that the interim file
     does not have yet are applied (Data Retention ignored; children's-privacy rows also get
     International and Specific Audiences).
  2. Long paragraphs. Paragraphs over --max-words words (default 300, about 400 RoBERTa
     tokens) are split at line and sentence boundaries into chunks of at most --max-words.
     Each chunk is labelled from the PolicyIE annotations: a practice is positive in the chunk
     that holds its trigger word. When only the practice's arguments reach into a chunk, that
     category is unknown there (mask 0) rather than negative.
  3. Text clean-up: broken UTF-8 sequences such as "â€" are repaired and invisible
     direction marks are removed. Curly quotes and dashes are kept.
  4. Headings. Rows with fewer than --min-words words (default 8) and no label are dropped.
  5. Five classes. A five-class label is positive when any of its ten-class labels is
     positive. It is known (mask 1) when it is positive or when every ten-class category
     feeding it was annotated; otherwise it is unknown (mask 0) and must not be used as a
     negative in training.
  6. Validation split. PolicyIE ships only train and test, so whole train policies are moved
     to validation (about --val-frac of train rows), with at least --min-val-pos positives for
     each class PolicyIE annotates.
  7. Leakage. Rows that share at least half their 8-word phrases with a row in a later split
     (train < validation < test) are dropped from the earlier split, checked within PolicyIE
     and against OPP-115 and GoPPC. Rows of those sources are never dropped here; any that copy
     PolicyIE evaluation rows are listed in other_rows_to_drop.csv (their own scripts drop them).
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

DEFAULT_RAW = ROOT.parent / "MSML641/PolicyIE/sanitized_split"
NEAR_DUP = 0.5  # same as policyie_preprocess.py and the combine step
SPLIT_RANK = {"train": 0, "validation": 1, "test": 2}
RETENTION = "Data Retention"
AUDIENCES = "International and Specific Audiences"
MOJIBAKE = [("â€™", "’"), ("â€˜", "‘"), ("â€œ", "“"), ("â€\x9d", "”"), ("â€“", "–"),
            ("â€”", "—"), ("â€", "”")]  # last one: closing quote whose third byte was lost
INVISIBLE = re.compile("[​-‏‪-‮⁠﻿]")


# ---------------------------------------------------------------- config

def load_configs(mapping_path, schema_path, policyie_path):
    doc = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    classes, mapping = doc["classes"], doc["opp115_to_five_class"]
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))["categories"]
    if len(classes) != 5 or len(set(classes)) != 5:
        raise SystemExit("Mapping must define exactly five unique classes")
    if set(mapping) != set(schema):
        raise SystemExit(f"Mapping keys must equal the ten categories in {schema_path}")
    if {v for v in mapping.values() if v is not None} - set(classes):
        raise SystemExit("Unknown target classes in the five-class mapping")
    pie = json.loads(Path(policyie_path).read_text(encoding="utf-8"))
    return classes, mapping, schema, pie["policyie_to_opp115"], pie["corrections"]


# ---------------------------------------------------------------- raw annotations

def index_raw(raw):
    idx = {}
    for p in Path(raw).rglob("*.txt"):
        if "__MACOSX" in p.parts or not p.stem.isdigit():
            continue
        key = f"policyie:{p.parent.name}#{int(p.stem):04d}"
        if key in idx:
            raise SystemExit(f"Two raw files for {key}: {idx[key]} and {p}")
        idx[key] = p
    return idx


def read_raw(path):
    """Raw text (exact characters, so brat offsets line up) plus spans and events."""
    text = path.read_bytes().decode("utf-8")
    ann_path = path.with_suffix(".ann")
    spans, events, bad = {}, [], 0
    if ann_path.exists():
        for line in ann_path.read_bytes().decode("utf-8").splitlines():
            if line.startswith("T"):
                tid, info, *rest = line.split("\t")
                offs = [tuple(map(int, x.split())) for x in info.split(" ", 1)[1].split(";")]
                s, e = min(a for a, _ in offs), max(b for _, b in offs)
                spans[tid] = (s, e)
                if len(offs) == 1 and rest and text[s:e] != rest[0]:
                    bad += 1
            elif line.startswith("E"):
                items = line.split("\t")[1].split()
                practice, trigger = items[0].split(":")
                args = [x.split(":")[1] for x in items[1:] if ":" in x]
                events.append((practice, trigger, args))
    return text, spans, events, bad


def split_units(text, max_words):
    """(start, end) pieces: lines, then sentences, then hard word cuts, each <= max_words."""
    out = []
    for m in re.finditer(r"[^\n]+", text):
        s, e = m.span()
        if not text[s:e].strip():
            continue
        if len(text[s:e].split()) <= max_words:
            out.append((s, e))
            continue
        cuts = [s] + [s + x.end() for x in re.finditer(r"[.!?;:](?=\s)", text[s:e])] + [e]
        for a, b in zip(cuts, cuts[1:]):
            if not text[a:b].strip():
                continue
            if len(text[a:b].split()) <= max_words:
                out.append((a, b))
                continue
            words = [w.span() for w in re.finditer(r"\S+", text[a:b])]
            for i in range(0, len(words), max_words):
                out.append((a + words[i][0], a + words[min(i + max_words, len(words)) - 1][1]))
    return out


def pack(units, text, max_words):
    chunks, cur, n = [], None, 0
    for a, b in units:
        w = len(text[a:b].split())
        if cur and n + w <= max_words:
            cur, n = (cur[0], b), n + w
        else:
            if cur:
                chunks.append(cur)
            cur, n = (a, b), w
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- rows

def clean(text):
    for bad, good in MOJIBAKE:
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", INVISIBLE.sub("", text)).strip()


def apply_corrections(row, corrections, schema):
    """Bring the interim row in line with configs/policyie_mapping.json (idempotent)."""
    children = set(corrections["children_to_specific_audiences"])
    ignore = set(corrections["ignore_retention"])
    rid, changed = row["id"], False
    if rid in children | ignore:
        if RETENTION in row["labels"] or row["label_mask"][schema.index(RETENTION)]:
            row["labels"] = [c for c in row["labels"] if c != RETENTION]
            row["label_mask"][schema.index(RETENTION)] = 0
            changed = True
        if rid in children and AUDIENCES not in row["labels"]:
            row["labels"] = [c for c in schema if c in row["labels"] or c == AUDIENCES]
            row["label_mask"][schema.index(AUDIENCES)] = 1
            changed = True
    row["label_vec"] = [int(c in row["labels"]) for c in schema]
    return changed


def chunk_row(row, raw, max_words, schema, practice_map, corrections, stats):
    """Split one ten-class row into chunks labelled from its own annotations."""
    text, spans, events, bad = raw
    stats["span_text_mismatches"] += bad
    units = split_units(text, max_words)
    chunks = pack(units, text, max_words)
    if len(chunks) < 2:
        return [dict(row, parent_id=row["id"], chunk=None)]

    children = row["id"] in set(corrections["children_to_specific_audiences"])
    ignore = row["id"] in set(corrections["ignore_retention"]) | ({row["id"]} if children else set())
    found, out = set(), []
    for k, (cs, ce) in enumerate(chunks):
        pos, partial = set(), set()
        for practice, trig, args in events:
            cat = practice_map[practice]
            ts = spans[trig][0]
            if cs <= ts < ce:
                pos.add(cat)
                found.add(cat)
            elif any(spans[a][0] < ce and spans[a][1] > cs for a in args if a in spans):
                partial.add(cat)
        mask = list(row["label_mask"])
        if ignore:
            pos.discard(RETENTION)
        if children:
            pos.add(AUDIENCES)
        for cat in partial - pos:
            mask[schema.index(cat)] = 0
            stats["chunk_labels_masked_as_partial"] += 1
        labels = [c for c in schema if c in pos]
        out.append(dict(row, id=f"{row['id']}.c{k}", text=text[cs:ce], labels=labels,
                        label_vec=[int(c in labels) for c in schema], label_mask=mask,
                        parent_id=row["id"], chunk=f"{k + 1}/{len(chunks)}"))

    expected = {practice_map[p] for p, _, _ in events}
    if found != expected:
        raise SystemExit(f"{row['id']}: chunk labels {sorted(found)} != paragraph labels {sorted(expected)}")
    stats["paragraphs_chunked"] += 1
    stats["chunks_made"] += len(out)
    return out


def to_five(row, classes, mapping, schema):
    old, old_mask = row["labels"], row["label_mask"]
    if len(old_mask) != len(schema) or row["label_vec"] != [int(c in old) for c in schema]:
        raise SystemExit(f"{row['id']}: label_vec/label_mask do not match the ten-class schema order")
    if any(not old_mask[schema.index(l)] for l in old):
        raise SystemExit(f"{row['id']}: positive label on a masked category")
    new = sorted({mapping[l] for l in old if mapping[l]}, key=classes.index)
    mask = []
    for c in classes:
        sources = [schema.index(o) for o, t in mapping.items() if t == c]
        mask.append(int(c in new or all(old_mask[i] for i in sources)))
    return {
        "id": row["id"],
        "source": "policyie",
        "doc_id": row["doc_id"],
        "group_id": row["group_id"],
        "split": row["split"],
        "text": row["text"],
        "labels": new,
        "label_vec": [int(c in new) for c in classes],
        "label_mask": mask,
        "label_fractions": None,  # PolicyIE releases adjudicated labels only
        "parent_id": row["parent_id"],
        "chunk": row["chunk"],
        "orig_labels": list(old),
        "orig_label_mask": list(old_mask),
    }


# ---------------------------------------------------------------- splits and leakage

def make_validation(rows, classes, frac, min_pos, seed):
    """Move whole train policies to validation. Returns (policies, seed used)."""
    by_doc = defaultdict(list)
    for r in rows:
        if r["split"] == "train":
            by_doc[r["doc_id"]].append(r)
    known = [i for i, c in enumerate(classes)
             if sum(r["label_vec"][i] for r in rows if r["split"] == "train") >= 2 * min_pos]
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
        if all(sum(r["label_vec"][i] for d in picked for r in by_doc[d]) >= min_pos for i in known):
            return sorted(picked), s
    raise SystemExit("Could not find a validation set with enough positives per class")


def find_leaks(pie_rows, opp_rows):
    """Pairs (lower, higher) where the lower-split row repeats the higher-split row."""
    rows = [("policyie", r) for r in pie_rows] + [(r["source"], r) for r in opp_rows]
    sh = [shingles(r["text"]) for _, r in rows]
    keys = [text_key(r["text"]) for _, r in rows]
    index = defaultdict(set)
    for i, s in enumerate(sh):
        for g in s:
            index[g].add(i)
    by_key = defaultdict(list)
    for i, k in enumerate(keys):
        by_key[k].append(i)

    leaks = []
    for i, (src, r) in enumerate(rows):
        if src != "policyie":
            continue
        cand = Counter(j for g in sh[i] for j in index[g] if j != i)
        hits = {j: n / max(1, min(len(sh[i]), len(sh[j]))) for j, n in cand.items()}
        for j in by_key[keys[i]]:
            if j != i:
                hits[j] = 1.0
        for j, share in hits.items():
            if share < NEAR_DUP or (rows[j][0] == "policyie" and j < i):
                continue  # each PolicyIE pair once
            a, b = (i, j)
            ra, rb = SPLIT_RANK[rows[a][1]["split"]], SPLIT_RANK[rows[b][1]["split"]]
            if ra == rb:
                continue
            low, high = (a, b) if ra < rb else (b, a)
            leaks.append((rows[low], rows[high], round(share, 2)))
    return leaks


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=ROOT / "data/interim/policyie.jsonl")
    ap.add_argument("--raw", default=DEFAULT_RAW, help="PolicyIE sanitized_split folder (for spans)")
    ap.add_argument("--opp115", default=ROOT / "data/interim/opp115_five_class.jsonl",
                    help="five-class OPP-115 rows for the leakage check ('' to skip)")
    ap.add_argument("--goppc", default=ROOT / "data/interim/goppc_five_class.jsonl",
                    help="five-class GoPPC rows for the leakage check ('' to skip)")
    ap.add_argument("--out", default=ROOT / "data/interim/policyie_five_class.jsonl")
    ap.add_argument("--mapping", default=ROOT / "configs/five_class_mapping.json")
    ap.add_argument("--schema", default=ROOT / "configs/label_schema.json")
    ap.add_argument("--policyie-config", default=ROOT / "configs/policyie_mapping.json")
    ap.add_argument("--report-dir", default=ROOT / "preprocessing/reports/policyie_five_class")
    ap.add_argument("--max-words", type=int, default=300, help="split paragraphs longer than this")
    ap.add_argument("--min-words", type=int, default=8, help="drop unlabelled rows shorter than this")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--min-val-pos", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    classes, mapping, schema, practice_map, corrections = load_configs(
        args.mapping, args.schema, args.policyie_config)
    rep_dir = Path(args.report_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)
    stats, log = Counter(), []
    rows = [json.loads(l) for l in open(args.inp, encoding="utf-8") if l.strip()]
    stats["input_rows"] = len(rows)

    # 1. corrections
    corrected = [r["id"] for r in rows if apply_corrections(r, corrections, schema)]
    known_ids = {r["id"] for r in rows}
    missing = (set(corrections["children_to_specific_audiences"]) | set(corrections["ignore_retention"])) - known_ids
    if missing:
        raise SystemExit(f"Correction ids not in the input: {sorted(missing)}")

    # 2. chunk long paragraphs
    raw_index = index_raw(args.raw) if Path(args.raw).exists() else None
    if raw_index is None:
        raise SystemExit(f"Raw PolicyIE folder not found: {args.raw} (pass --raw)")
    chunked = []
    for r in rows:
        if len(r["text"].split()) <= args.max_words:
            chunked.append(dict(r, parent_id=r["id"], chunk=None))
            continue
        path = raw_index.get(r["id"])
        if path is None:
            raise SystemExit(f"No raw file for {r['id']}")
        raw = read_raw(path)
        if re.sub(r"\s+", " ", raw[0]).strip() != r["text"]:
            raise SystemExit(f"{r['id']}: raw text does not match the interim text")
        chunked.extend(chunk_row(r, raw, args.max_words, schema, practice_map, corrections, stats))

    # 3. clean text; 4. drop headings; 5. five classes
    out_rows, dropped = [], []
    for r in chunked:
        before = re.sub(r"\s+", " ", r["text"]).strip()
        r["text"] = clean(r["text"])
        if r["text"] != before:
            stats["rows_text_repaired"] += 1
        if len(r["text"].split()) < args.min_words and not r["labels"]:
            dropped.append((r["id"], r["split"], "heading (short, no label)", "", r["text"]))
            continue
        out_rows.append(to_five(r, classes, mapping, schema))

    # 6. validation split
    val_docs, used_seed = make_validation(out_rows, classes, args.val_frac, args.min_val_pos, args.seed)
    for r in out_rows:
        if r["doc_id"] in val_docs:
            r["split"] = "validation"

    # 7. leakage
    opp_rows = []
    for name, p in (("OPP-115", args.opp115), ("GoPPC", args.goppc)):
        if p and Path(p).exists():
            opp_rows += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        else:
            log.append(f"{name} leakage check skipped (file not found)")
    leaks = find_leaks(out_rows, opp_rows)
    drop_ids, opp_drop = {}, {}
    for (lsrc, low), (hsrc, high), share in leaks:
        if lsrc == "policyie":
            drop_ids.setdefault(low["id"], (high["id"], high["split"], share))
        else:
            opp_drop.setdefault(low["id"], (low["split"], high["id"], high["split"], share))
    for r in out_rows:
        if r["id"] in drop_ids:
            hid, hsplit, share = drop_ids[r["id"]]
            dropped.append((r["id"], r["split"], f"near-copy of {hsplit} row", f"{hid} ({share})", r["text"]))
    out_rows = [r for r in out_rows if r["id"] not in drop_ids]

    if len({r["id"] for r in out_rows}) != len(out_rows):
        raise SystemExit("Duplicate ids in output")
    assert all(m for r in out_rows for c, m, v in zip(classes, r["label_mask"], r["label_vec"]) if v)
    assert all(len(r["text"].split()) <= args.max_words for r in out_rows)

    # write
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(rep_dir / "dropped_rows.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "split", "reason", "matched_row", "text_start"),
                                 *[(a, b, c, d, e[:200]) for a, b, c, d, e in dropped]])
    with open(rep_dir / "other_rows_to_drop.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("id", "split", "policyie_id", "policyie_split", "share"),
                                 *[(k, *v) for k, v in sorted(opp_drop.items())]])

    splits = sorted({r["split"] for r in out_rows}, key=SPLIT_RANK.get)
    pos = {s: Counter() for s in splits}
    known = {s: Counter() for s in splits}
    for r in out_rows:
        pos[r["split"]].update(r["labels"])
        known[r["split"]].update(c for c, m in zip(classes, r["label_mask"]) if m)
    words = sorted(len(r["text"].split()) for r in out_rows)
    report = {
        "input_file": str(args.inp),
        "raw_folder": str(args.raw),
        "output_file": str(out_path),
        "classes": classes,
        "mapping": mapping,
        "steps": {
            "1_corrections_applied_now": corrected,
            "2_paragraphs_chunked": stats["paragraphs_chunked"],
            "2_chunks_made": stats["chunks_made"],
            "2_max_words": args.max_words,
            "2_chunk_labels_masked_as_partial": stats["chunk_labels_masked_as_partial"],
            "2_span_text_mismatches": stats["span_text_mismatches"],
            "3_rows_text_repaired": stats["rows_text_repaired"],
            "4_heading_rows_dropped": sum(1 for d in dropped if d[2].startswith("heading")),
            "6_validation_policies": val_docs,
            "6_validation_seed": used_seed,
            "7_policyie_rows_dropped_for_leakage": len(drop_ids),
            "7_other_rows_to_drop_in_combine": len(opp_drop),
        },
        "rows": len(out_rows),
        "rows_by_split": {s: sum(1 for r in out_rows if r["split"] == s) for s in splits},
        "policies_by_split": {s: len({r["doc_id"] for r in out_rows if r["split"] == s}) for s in splits},
        "rows_with_no_class": sum(1 for r in out_rows if not r["labels"]),
        "words": {"min": words[0], "median": words[len(words) // 2], "max": words[-1]},
        "positives_by_class_and_split": {s: {c: pos[s][c] for c in classes} for s in splits},
        "known_rows_by_class_and_split (mask = 1)": {s: {c: known[s][c] for c in classes} for s in splits},
        "mask_patterns": dict(Counter(str(r["label_mask"]) for r in out_rows)),
        "notes": log + [
            "Positive if any source category is positive; mask 1 when positive or every source category was annotated.",
            "Chunks inherit the paragraph's doc_id, so they stay in the same split.",
            "GoPPC rows that copy PolicyIE validation/test rows must be dropped in the combine step.",
        ],
    }
    (rep_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("steps", "rows_by_split", "policies_by_split", "words",
                                             "positives_by_class_and_split")}, indent=2))


if __name__ == "__main__":
    main()
