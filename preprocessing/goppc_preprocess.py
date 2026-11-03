"""Convert a GoPPC document-split CSV into a separate five-class JSONL task.

This task uses the five broad classes in configs/goppc_mapping.json. It does not
change Inkwell's ten-category schema. The CSV stores taxonomy IDs, so populate
concept_id_to_class from the official GoPPC taxonomy before using the rows to train.

Example:
    python preprocessing/goppc_preprocess.py \
      --csv /path/to/p_dataset_document_train.csv \
      --mapping configs/goppc_mapping.json \
      --out data/interim/goppc_train.jsonl

Rows with blank text and exact duplicate text are skipped and described in the
report. The supplied CSV split is preserved as `train`; do not make a random
row-level split from this file.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data/raw/goppc/p_dataset_document_train.csv"


def norm_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


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
    ap.add_argument("--out", default=ROOT / "data/interim/goppc_train.jsonl")
    ap.add_argument("--report", default=ROOT / "preprocessing/reports/goppc/report.json")
    ap.add_argument("--doc-id-column", default=None,
                    help="CSV column containing stable policy/document IDs; omit if unavailable")
    args = ap.parse_args()

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

        for row_num, raw in enumerate(reader, start=2):
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
            doc_id_value = (raw.get(args.doc_id_column, "").strip()
                            if args.doc_id_column else "")
            doc_id = f"goppc:{doc_id_value}" if doc_id_value else None
            unit_id = f"goppc:train:{row_num}"

            # Keep source structure for later context-aware use and audit. The numeric
            # columns are copied as metadata; this script does not interpret them.
            metadata = {
                key: raw.get(key, "")
                for key in ("parents", "siblings", "parents_matrix", "siblings_matrix")
            }
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
                "split": "train",
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
        "split": "train (inherited from input filename; no new split made)",
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
            "Recover stable policy IDs before merging or evaluating with policy-level splits.",
            "The supplied file is a training split; it cannot serve as validation or test data.",
            "Numeric columns and hierarchy/context fields are preserved but not interpreted as model inputs.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "output": str(out_path), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
