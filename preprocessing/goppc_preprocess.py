"""Convert a GoPPC document-split CSV into a separate five-class JSONL task.

This task uses the five broad classes in configs/goppc_mapping.json. It does not
change Inkwell's ten-category schema. The CSV stores taxonomy IDs, so populate
concept_id_to_class from the official GoPPC taxonomy before using the rows to train.

Example:
    python preprocessing/goppc_preprocess.py \
      --csv data/raw/goppc/p_dataset_document_train.csv \
      --out data/interim/goppc_train.jsonl
    python preprocessing/goppc_preprocess.py \
      --csv data/raw/goppc/p_dataset_document_test.csv \
      --out data/interim/goppc_test.jsonl

Rows with blank text and exact duplicate text are skipped and described in the
report. The split is taken from the CSV file name (train or test); do not make a
random row-level split from these files.

Policy IDs: the CSVs have no document column, so each row is matched to one of the
150 policies in data/raw/goppc/GoPPC-150/<n>.xml (downloaded from the GoPPC repository)
by shared 4-word phrases. The CSVs list paragraphs in document order, so rows that do
not match one policy clearly (short headings, list items) take the policy of the
surrounding rows. doc_id is then `goppc:<n>`, and Web_list.csv gives the website name.
"""
import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/raw/goppc/p_dataset_document_train.csv"
DEFAULT_XML = ROOT / "data/raw/goppc/GoPPC-150"
DEFAULT_WEB = ROOT / "data/raw/goppc/Web_list.csv"
MATCH_N = 4            # words per phrase when matching rows to policies
MATCH_SHARE = 0.8      # a confident match covers this share of the row's phrases ...
MATCH_MARGIN = 0.2     # ... and beats the next-best policy by this much


def norm_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def phrases(text):
    w = words(text)
    return [" ".join(w[i:i + MATCH_N]) for i in range(len(w) - MATCH_N + 1)]


def match_policies(texts, xml_dir):
    """Policy number for each row, plus how it was found ('phrase' or 'neighbour')."""
    index = defaultdict(set)
    for p in Path(xml_dir).glob("*.xml"):
        # Some files are not well-formed XML, so strip tags instead of parsing.
        raw = html.unescape(re.sub(r"<[^>]+>", " ", p.read_text(encoding="utf-8", errors="replace")))
        for g in phrases(raw):
            index[g].add(int(p.stem))
    if not index:
        raise SystemExit(f"No policy XML files found in {xml_dir}")

    scores = []
    for t in texts:
        g = phrases(t)
        c = Counter(d for x in g for d in index.get(x, ()))
        scores.append({d: n / len(g) for d, n in c.items()} if g else {})
    sure = []
    for s in scores:
        top = sorted(s.items(), key=lambda kv: -kv[1])[:2]
        ok = top and top[0][1] >= MATCH_SHARE and top[0][1] - (top[1][1] if len(top) > 1 else 0) >= MATCH_MARGIN
        sure.append(top[0][0] if ok else None)

    # Confident matches must form one unbroken run per policy (the CSV is in document order).
    seq = [d for d in sure if d is not None]
    runs = [d for i, d in enumerate(seq) if i == 0 or d != seq[i - 1]]
    if len(runs) != len(set(runs)):
        raise SystemExit("Confident policy matches are not in one run per policy; check the CSV order")

    out = []
    for i, d in enumerate(sure):
        if d is not None:
            out.append((d, "phrase"))
            continue
        prev = next((sure[j] for j in range(i - 1, -1, -1) if sure[j] is not None), None)
        nxt = next((sure[j] for j in range(i + 1, len(sure)) if sure[j] is not None), None)
        options = [x for x in (prev, nxt) if x is not None]
        if not options:
            out.append((None, "unmatched"))
            continue
        best = max(options, key=lambda x: (scores[i].get(x, 0), x == prev))
        out.append((best, "neighbour"))
    return out


def read_web_list(path):
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {int(r["Number"]): r["Web"].strip() for r in csv.DictReader(f) if r.get("Number", "").strip().isdigit()}


def parse_concepts(value):
    """Preserve concept IDs from every semicolon-delimited label component."""
    return sorted({
        token.strip()
        for group in (value or "").split(";")
        for token in group.split(",")
        if token.strip()
    })


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV, help=f"GoPPC CSV (default: {DEFAULT_CSV})")
    ap.add_argument("--mapping", default=ROOT / "configs/goppc_mapping.json",
                    help="GoPPC ID-to-five-class mapping JSON")
    ap.add_argument("--split", default=None, choices=["train", "test"],
                    help="split of the CSV (default: taken from the file name)")
    ap.add_argument("--out", default=None, help="default: data/interim/goppc_<split>.jsonl")
    ap.add_argument("--report", default=None,
                    help="default: preprocessing/reports/goppc/report.json (train) or report_<split>.json")
    ap.add_argument("--doc-id-column", default=None,
                    help="CSV column containing stable policy/document IDs; omit to match rows to --xml-dir")
    ap.add_argument("--xml-dir", default=DEFAULT_XML, help="GoPPC-150 policy XML files")
    ap.add_argument("--web-list", default=DEFAULT_WEB, help="GoPPC Web_list.csv (policy number -> website)")
    args = ap.parse_args()

    split = args.split or ("test" if "_test" in Path(args.csv).name else "train")
    args.out = args.out or ROOT / f"data/interim/goppc_{split}.jsonl"
    args.report = args.report or ROOT / ("preprocessing/reports/goppc/report.json" if split == "train"
                                         else f"preprocessing/reports/goppc/report_{split}.json")
    websites = read_web_list(args.web_list)

    mapping_doc = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    classes = mapping_doc.get("classes", [])
    mapping = mapping_doc.get("concept_id_to_class", {})
    covered = mapping_doc.get("covered_classes", [])
    if len(classes) != 5 or len(set(classes)) != 5:
        raise SystemExit("Mapping config must define exactly five unique classes")
    unknown_classes = (set(mapping.values()) | set(covered)) - set(classes)
    if unknown_classes:
        raise SystemExit(f"Unknown GoPPC target classes in mapping: {sorted(unknown_classes)}")
    if set(mapping.values()) - set(covered):
        raise SystemExit("Every class used by a concept ID must be listed in covered_classes")

    out_path, report_path = Path(args.out), Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    seen_rows = set()
    source_concepts = Counter()
    mapped_counts = Counter()
    unknown_concepts = Counter()

    with open(args.csv, encoding="utf-8-sig", newline="") as src, \
            open(out_path, "w", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        required = {"text", "label"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV is missing required columns: {sorted(missing)}")
        if args.doc_id_column and args.doc_id_column not in (reader.fieldnames or []):
            raise SystemExit(f"Document ID column not found: {args.doc_id_column}")
        all_rows = list(reader)
        if args.doc_id_column:
            matches = [(r.get(args.doc_id_column, "").strip() or None, "column") for r in all_rows]
        else:
            matches = match_policies([norm_text(r.get("text")) for r in all_rows], args.xml_dir)
        counts.update(f"doc_id_by_{how}" for _, how in matches)

        for row_num, (raw, (doc_value, _how)) in enumerate(zip(all_rows, matches), start=2):
            counts["input_rows"] += 1
            text = norm_text(raw.get("text"))
            if not text:
                counts["blank_text_rows"] += 1
                continue
            concepts = parse_concepts(raw.get("label"))
            key = hashlib.sha256(
                (text.casefold() + "\0" + "\0".join(concepts)).encode("utf-8")
            ).hexdigest()
            if key in seen_rows:
                counts["exact_duplicate_text_and_label_rows"] += 1
                continue
            seen_rows.add(key)

            source_concepts.update(concepts)
            labels = sorted({mapping[c] for c in concepts if c in mapping}, key=classes.index)
            mapped_counts.update(labels)
            unknown_concepts.update(c for c in concepts if c not in mapping)
            mask = [int(category in covered) for category in classes]
            doc_id = f"goppc:{doc_value}" if doc_value is not None else None
            unit_id = f"goppc:{split}:{row_num}"

            # Keep source structure for later context-aware use and audit. The numeric
            # columns are copied as metadata; this script does not interpret them.
            metadata = {
                key: raw.get(key, "")
                for key in ("parents", "siblings", "parents_matrix", "siblings_matrix")
            }
            metadata["website"] = websites.get(doc_value) if isinstance(doc_value, int) else None
            metadata["numeric_columns_uninterpreted"] = {
                key: raw[key] for key in raw if key.isdigit()
            }
            record = {
                "source": "goppc",
                "doc_id": doc_id,
                "group_id": doc_id,
                "unit_id": unit_id,
                "text": text,
                "labels": labels,
                "label_mask": mask,
                "spans": [],
                "split": split,
                "orig_label": raw.get("label", ""),
                "orig_concepts": concepts,
                "metadata": metadata,
            }
            dst.write(json.dumps(record, ensure_ascii=False) + "\n")
            counts["kept_rows"] += 1
            if not doc_id:
                counts["rows_missing_doc_id"] += 1

    report = {
        "source_file": str(Path(args.csv)),
        "output_file": str(out_path),
        "split": f"{split} (inherited from input filename; no new split made)",
        "policies": len({d for d, _ in matches if d is not None}),
        "task_classes": classes,
        "covered_classes": covered,
        "concept_id_to_class": mapping,
        "concept_families_from_project_mapping": mapping_doc.get("concept_families", {}),
        "counts": dict(counts),
        "mapped_positive_rows_by_category": dict(mapped_counts),
        "original_concept_frequency": dict(source_concepts),
        "unmapped_concept_frequency": dict(unknown_concepts),
        "limitations": [
            "Confirm the source dataset defines semicolon-separated label groups as a set of concepts before training.",
            "Confirm covered_classes are exhaustively annotated before treating masked zero labels as negatives.",
            "Policy IDs are recovered by matching text to the GoPPC-150 XML files; rows matched only through their neighbours are counted under doc_id_by_neighbour.",
            "The upstream release has train and test only; validation is made from whole train policies in goppc_to_five_class.py.",
            "Numeric columns and hierarchy/context fields are preserved but not interpreted as model inputs.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "output": str(out_path), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
