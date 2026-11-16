"""Recover original OPP-115 attributes and export a sale-practice review queue.

python -m scripts.sale_review export --root /tmp/inkwell-opp115-v1.zip --out data/review/sale-v1
python -m scripts.sale_review validate --batch data/review/sale-v1 --reviewed reviewed.jsonl --out accepted.jsonl
"""
import argparse
import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from preprocessing.opp115_preprocess import clean_with_map, remap_span

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "configs/sale_annotation_schema.json"
SALE = re.compile(r"\b(?:sell(?:s|ing)?|sold|resell(?:s|ing)?|resold|sale|sales)\b", re.I)


def digest(path):
    with Path(path).open("rb") as stream:
        hasher = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
        return hasher.hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_rows(path, rows):
    with Path(path).open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_original(root):
    """Read only required files. Zip paths are never extracted to the filesystem."""
    root = Path(root)
    if root.suffix.lower() == ".zip":
        with zipfile.ZipFile(root) as archive:
            files = {}
            for path in archive.namelist():
                if path.startswith("__MACOSX/") or path.endswith("/"):
                    continue
                parts = path.split("/")
                if not any(part in {"annotations", "sanitized_policies", "documentation"} for part in parts):
                    continue
                files[path] = archive.read(path).decode("utf-8")
    else:
        if not (root / "annotations").is_dir():
            root = root / "OPP-115"
        files = {str(p.relative_to(root)): p.read_bytes().decode("utf-8")
                 for folder in ("annotations", "sanitized_policies", "documentation")
                 for p in (root / folder).rglob("*") if p.is_file() and p.suffix in {".csv", ".html", ".xml", ".txt"}}
    policies, annotations, errant = {}, defaultdict(list), set()
    schema_xml = None
    for path, contents in sorted(files.items()):
        parts = path.split("/")
        prefix = parts[-1].split("_")[0]
        if "sanitized_policies" in parts:
            if prefix in policies:
                raise ValueError(f"Duplicate policy prefix: {prefix}")
            policies[prefix] = contents.split("|||")
        elif "annotations" in parts and path.endswith(".csv"):
            for row in csv.reader(io.StringIO(contents)):
                if len(row) != 9:
                    raise ValueError(f"Expected nine annotation columns in {path}")
                annotations[(prefix, int(row[4]))].append({
                    "annotation_id": row[0], "annotator_id": row[2], "category": row[5],
                    "attributes": json.loads(row[6]), "source_file": path,
                })
        elif "errant_span_indexes" in parts and path.endswith(".csv"):
            for line in contents.splitlines():
                if "," in line:
                    annotation_id, name = line.split(",", 1)
                    errant.add((annotation_id.strip(), re.sub(r"^\d+_", "", name.strip())))
        elif parts[-1] == "categories-july30.xml":
            schema_xml = contents
    if not policies or not annotations or schema_xml is None:
        raise ValueError("Original annotations, sanitized policies and category XML are required")
    return policies, annotations, errant, schema_xml


def map_attribute(attribute, raw, clean, source_indices, known_bad=False):
    """Preserve source fields; expose usable spans only when their text is verified."""
    result = {"value": attribute.get("value"), "original": dict(attribute), "span": None}
    start, end = attribute.get("startIndexInSegment"), attribute.get("endIndexInSegment")
    selected = attribute.get("selectedText")
    if known_bad:
        result["span_status"] = "known_errant"
    elif not isinstance(selected, str) or not selected.strip() or not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        result["span_status"] = "not_selected"
    else:
        status = "exact"
        if not 0 <= start < end <= len(raw) or raw[start:end] != selected:
            occurrences = [m.start() for m in re.finditer(re.escape(selected), raw)]
            if len(occurrences) != 1:
                result["span_status"] = "ambiguous" if occurrences else "unmatched"
                return result
            start, end = occurrences[0], occurrences[0] + len(selected)
            status = "repaired_unique"
        mapped = remap_span(clean, source_indices, start, end)
        result["span_status"] = status if mapped else "removed_by_cleaning"
        if mapped:
            a, b = mapped
            result["span"] = {"start": a, "end": b, "text": clean[a:b]}
            result["verified_raw_span"] = {"start": start, "end": end, "text": raw[start:end]}
    return result


def schema_inventory(xml):
    ns = {"x": "http://www.w3schools.com"}
    root = ET.fromstring(xml)
    inventory = {}
    for category in root.findall("x:category", ns):
        if category.findtext("x:name", namespaces=ns) != "Third Party Sharing/Collection":
            continue
        for attr in category.findall("x:attributes/x:attribute", ns):
            name = attr.findtext("x:name", namespaces=ns)
            inventory[name] = {"default": attr.get("default"),
                               "values": [v.text for v in attr.findall("x:values/x:value/x:name", ns)]}
    return inventory


def export_batch(root, dataset, out):
    if out.exists():
        raise ValueError("Output folder exists; choose a new version to preserve reviews")
    policies, annotations, errant, xml = read_original(root)
    rows = [r for r in read_rows(dataset) if r["source"] == "opp115"]
    selected, span_counts = [], Counter()
    for row in rows:
        matches = list(SALE.finditer(row["text"]))
        if not matches:
            continue
        prefix, index = row["id"].removeprefix("opp115:").split("#")
        raw = policies[prefix][int(index)]
        clean, source_indices = clean_with_map(raw)
        if clean != row["text"]:
            raise ValueError(f"Original/benchmark text mismatch: {row['id']}")
        recovered = []
        for annotation in annotations[(prefix, int(index))]:
            attrs = {}
            for name, attribute in annotation["attributes"].items():
                attrs[name] = map_attribute(attribute, raw, clean, source_indices,
                                            (annotation["annotation_id"], name) in errant)
                span_counts[attrs[name]["span_status"]] += 1
            recovered.append({**annotation, "attributes": attrs})
        selected.append({k: row[k] for k in ("id", "doc_id", "group_id", "split", "text")} | {
            "source_labels": row["labels"], "raw_segment": raw,
            "candidate_spans": [{"start": m.start(), "end": m.end(), "text": m.group()} for m in matches],
            "original_annotations": recovered,
            "review": {"sale_related": None, "practices": [], "reviewer": "", "adjudicator": "", "notes": ""},
        })
    groups = defaultdict(set)
    texts = defaultdict(set)
    for row in selected:
        groups[row["group_id"]].add(row["split"])
        texts[re.sub(r"[^a-z0-9]", "", row["text"].lower())].add(row["split"])
    if any(len(s) > 1 for s in list(groups.values()) + list(texts.values())):
        raise ValueError("Candidate batch contains cross-split company/text leakage")
    inventory = schema_inventory(xml)
    out.mkdir(parents=True)
    write_rows(out / "candidates.jsonl", selected)
    for split in ("train", "validation", "test"):
        write_rows(out / f"{split}.jsonl", [r for r in selected if r["split"] == split])
    (out / "annotation_schema.json").write_text(SCHEMA.read_text())
    manifest = {
        "schema_version": json.loads(SCHEMA.read_text())["version"],
        "source_url": "https://usableprivacy.org/static/data/OPP-115_v1_0.zip",
        "source_sha256": digest(root) if root.is_file() else None,
        "dataset_sha256": digest(dataset), "schema_sha256": digest(SCHEMA),
        "candidate_sha256": digest(out / "candidates.jsonl"),
        "files_sha256": {f"{s}.jsonl": digest(out / f"{s}.jsonl") for s in ("train", "validation", "test")},
        "eligible_opp115_segments": len(rows), "candidate_segments": len(selected),
        "candidate_policies": len({r["doc_id"] for r in selected}),
        "splits": dict(Counter(r["split"] for r in selected)),
        "attribute_span_statuses": dict(span_counts), "third_party_attribute_schema": inventory,
        "selection": SALE.pattern,
        "contract": "Unreviewed keyword candidates, not gold labels. Retained frozen v1 splits; no category gate; known errant spans unusable; repairs require a unique text match. Does is a source default, not an explicit sale assertion.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = ["# Sale annotation review queue", "", "Unreviewed candidates. Start with train.jsonl; keep test.jsonl sealed until final evaluation.", "",
             f"{len(selected)} segments from {manifest['candidate_policies']} policies; splits: {manifest['splits']}.", "",
             "Original attributes and verified spans are in JSONL. Keyword matches are navigation aids, not practice evidence or target labels.", "",
             "## Training candidates", ""]
    for row in selected:
        if row["split"] != "train":
            continue
        lines.extend([f"### {row['id']}", "", "> " + row["text"].replace("\n", "\n> "), ""])
        for ann in row["original_annotations"]:
            if ann["category"] != "Third Party Sharing/Collection":
                continue
            attrs = ann["attributes"]
            polarity = attrs.get("Does/Does Not", {}).get("value")
            action = attrs.get("Action Third Party", {}).get("span")
            lines.append(f"- Annotator {ann['annotator_id']}, annotation {ann['annotation_id']}: polarity={polarity}; action={json.dumps(action, ensure_ascii=False)}")
        lines.append("")
    (out / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest


def load_batch(batch):
    manifest = json.loads((batch / "manifest.json").read_text())
    if digest(batch / "candidates.jsonl") != manifest["candidate_sha256"]:
        raise ValueError("Candidate source changed")
    if digest(batch / "annotation_schema.json") != manifest["schema_sha256"]:
        raise ValueError("Annotation schema changed")
    return manifest, {r["id"]: r for r in read_rows(batch / "candidates.jsonl")}


def review_issues(rows, originals, schema, require_adjudication=True):
    """Check all records; audit mode preserves author provenance without accepting it."""
    issues, seen = [], set()

    def issue(line, path, message):
        issues.append({"line": line, "path": path, "message": message})

    if not rows:
        issue(0, "", "Review must be nonempty")
    for line, row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            issue(line, "id", "Record requires a string ID")
            continue
        if row["id"] in seen:
            issue(line, "id", "Repeated ID")
        seen.add(row["id"])
        original = originals.get(row["id"])
        if original is None or {k: v for k, v in row.items() if k != "review"} != {k: v for k, v in original.items() if k != "review"}:
            issue(line, "", "Source metadata changed or ID is unknown")
            continue
        review = row.get("review")
        if not isinstance(review, dict):
            issue(line, "review", "Review must be an object")
            continue
        if type(review.get("sale_related")) is not bool:
            issue(line, "review.sale_related", "sale_related requires an explicit boolean")
        if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
            issue(line, "review.reviewer", "Author identifier required; preserve original attribution")
        if require_adjudication:
            if not all(isinstance(review.get(k), str) and review[k].strip() for k in ("reviewer", "adjudicator")) or review["reviewer"].strip() == review["adjudicator"].strip():
                issue(line, "review.adjudicator", "Two distinct human reviewer identifiers required")
        elif not isinstance(review.get("adjudicator"), str):
            issue(line, "review.adjudicator", "Adjudicator must be a string; empty is allowed in a draft")
        notes = review.get("notes")
        if not isinstance(notes, str):
            issue(line, "review.notes", "Notes must be a string")
        elif review.get("sale_related") is False and not notes.strip():
            issue(line, "review.notes", "Explain why the candidate is not sale-related")
        practices = review.get("practices")
        if not isinstance(practices, list):
            issue(line, "review.practices", "Practices must be a list")
            continue
        if bool(practices) != review.get("sale_related"):
            issue(line, "review.practices", "Sale-related records require practices; rejected records must have none")
        for index, practice in enumerate(practices):
            path = f"review.practices[{index}]"
            if not isinstance(practice, dict):
                issue(line, path, "Practice must be an object")
                continue
            if not isinstance(practice.get("label"), str) or practice["label"] not in schema["labels"]:
                issue(line, path + ".label", "Unknown practice label")
            if "practice_types" in schema and (not isinstance(practice.get("practice_type"), str) or practice["practice_type"] not in schema["practice_types"]):
                issue(line, path + ".practice_type", "Unknown or missing practice type")
            fields = schema.get("span_fields", {k: "" for k in ("evidence", "conditions", "exceptions")})
            for field in fields:
                spans = practice.get(field)
                if not isinstance(spans, list) or (field == "evidence" and not spans):
                    issue(line, path + "." + field, "Span list required; evidence cannot be empty")
                    continue
                for span_index, span in enumerate(spans):
                    span_path = f"{path}.{field}[{span_index}]"
                    if not isinstance(span, dict):
                        issue(line, span_path, "Span must be an object")
                        continue
                    a, b = span.get("start"), span.get("end")
                    if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(row["text"]) or row["text"][a:b] != span.get("text"):
                        issue(line, span_path, "Evidence must match source character offsets exactly")
            if practice.get("label") == "conditional" and not (practice.get("conditions") or practice.get("exceptions")):
                issue(line, path, "Conditional practices require condition/exception evidence; scope or opt-outs alone do not qualify")
            if not isinstance(practice.get("notes"), str):
                issue(line, path + ".notes", "Practice notes must be a string")
            elif practice.get("label") == "unclear" and not practice["notes"].strip():
                issue(line, path + ".notes", "Unclear practices require an explanation")
    return issues


def normalize_review(reviewed, out):
    """Reformat complete JSON objects as JSONL; never guess missing content."""
    if out.exists() or out.with_suffix(".manifest.json").exists():
        raise FileExistsError("Output exists; choose a new version")
    text, decoder, cursor, rows = reviewed.read_text(), json.JSONDecoder(), 0, []
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        row, cursor = decoder.raw_decode(text, cursor)
        if not isinstance(row, dict):
            raise ValueError("Every record must be an object")
        rows.append(row)
    if not rows:
        raise ValueError("Input is empty")
    write_rows(out, rows)
    out.with_suffix(".manifest.json").write_text(json.dumps({
        "input_sha256": digest(reviewed), "output_sha256": digest(out), "records": len(rows),
        "operation": "Whitespace/JSON serialization normalization only; annotation values and provenance preserved.",
    }, indent=2) + "\n")
    return len(rows)


def audit_review(batch, reviewed, out, schema_path=SCHEMA):
    """Write a structural draft report without creating an accepted dataset."""
    if out.exists():
        raise FileExistsError("Audit output exists; choose a new version")
    manifest, originals = load_batch(batch)
    schema = json.loads(schema_path.read_text())
    rows, parse_issues = [], []
    for line, text in enumerate(reviewed.read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            rows.append((line, json.loads(text)))
        except ValueError as error:
            parse_issues.append({"line": line, "path": "", "message": f"Invalid JSONL: {error}"})
    issues = parse_issues + review_issues(rows, originals, schema, require_adjudication=False)
    practices = [p for _, r in rows if isinstance(r, dict) and isinstance(r.get("review"), dict)
                 and isinstance(r["review"].get("practices"), list)
                 for p in r["review"]["practices"] if isinstance(p, dict)]
    report = {
        "mode": "draft_audit", "passed": not issues, "records": len(rows),
        "schema_version": schema["version"], "schema_sha256": digest(schema_path),
        "batch_schema_version": manifest["schema_version"],
        "candidate_sha256": manifest["candidate_sha256"], "input_sha256": digest(reviewed),
        "practice_types": dict(Counter(str(p.get("practice_type", "missing")) for p in practices)),
        "labels": dict(Counter(str(p.get("label", "missing")) for p in practices)),
        "span_counts": {field: sum(len(p[field]) for p in practices if isinstance(p.get(field), list))
                        for field in schema.get("span_fields", {k: "" for k in ("evidence", "conditions", "exceptions")})},
        "issues": issues,
        "contract": "Structural draft audit only. Does not certify semantic accuracy, accept training data, or change annotation provenance.",
    }
    with out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    return report


def validate_review(batch, reviewed, out, schema_path=None):
    if out.exists() or out.with_suffix(".manifest.json").exists():
        raise FileExistsError("Output exists; choose a new version")
    manifest, originals = load_batch(batch)
    schema_path = schema_path or batch / "annotation_schema.json"
    schema = json.loads(schema_path.read_text())
    rows = read_rows(reviewed)
    issues = review_issues(list(enumerate(rows, 1)), originals, schema)
    if issues:
        first = issues[0]
        raise ValueError(f"Line {first['line']} {first['path']}: {first['message']} ({len(issues)} issue(s))")
    write_rows(out, rows)
    out.with_suffix(".manifest.json").write_text(json.dumps({
        "schema_version": schema["version"], "schema_sha256": digest(schema_path),
        "batch_schema_sha256": manifest["schema_sha256"],
        "candidate_sha256": manifest["candidate_sha256"], "reviewed_input_sha256": digest(reviewed),
        "accepted_sha256": digest(out), "records": len(rows),
        "contract": "Structural validation only; reviewer identifiers do not establish annotation quality or inter-reviewer agreement.",
    }, indent=2) + "\n")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--root", type=Path, required=True)
    export.add_argument("--dataset", type=Path, default=ROOT / "data/versions/v1/classifier.jsonl")
    export.add_argument("--out", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--batch", type=Path, required=True)
    validate.add_argument("--reviewed", type=Path, required=True)
    validate.add_argument("--out", type=Path, required=True)
    validate.add_argument("--schema", type=Path, help="Use a newer schema without modifying the batch snapshot")
    audit = sub.add_parser("audit", help="Report all structural errors in a draft without accepting it")
    audit.add_argument("--batch", type=Path, required=True)
    audit.add_argument("--reviewed", type=Path, required=True)
    audit.add_argument("--schema", type=Path, default=SCHEMA)
    audit.add_argument("--out", type=Path, required=True)
    normalize = sub.add_parser("normalize", help="Write complete JSON records as one object per line")
    normalize.add_argument("--reviewed", type=Path, required=True)
    normalize.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        result = export_batch(args.root, args.dataset, args.out)
        print(json.dumps({k: result[k] for k in ("candidate_segments", "candidate_policies", "splits", "attribute_span_statuses")}, indent=2))
    elif args.command == "validate":
        print(f"Validated {validate_review(args.batch, args.reviewed, args.out, args.schema)} reviewed records")
    elif args.command == "normalize":
        print(f"Normalized {normalize_review(args.reviewed, args.out)} records without changing annotation values")
    else:
        report = audit_review(args.batch, args.reviewed, args.out, args.schema)
        print(f"Draft audit: {report['records']} records, {len(report['issues'])} issue(s)")
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
