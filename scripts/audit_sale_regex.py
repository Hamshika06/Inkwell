"""Audit stored regex flags against source text without changing frozen results."""
import argparse
import json
from pathlib import Path

from inkwell.risk import COMPILED
from scripts.sale_review import digest, read_rows


CONTROLS = (
    ("We sell your personal information.", True, "Supported affirmative sale"),
    ("We may sell your personal data.", True, "Supported modal sale"),
    ("We will sell personal information.", True, "Supported future sale"),
    ("We do not sell your personal information.", False, "Denial is not an affirmative risk flag"),
    ("We will not sell your personal information.", False, "Future denial is not an affirmative risk flag"),
    ('We "rent" our marketing list.', False, "Rental wording is unsupported by the legacy rule"),
)


def audit_regex(prediction_path, source_path, out):
    if out.exists():
        raise ValueError("Audit exists; choose a new output directory")
    rule, pattern = next((r, p) for r, p in COMPILED if r.id == "data_sale")
    source = read_rows(source_path)
    predictions = read_rows(prediction_path)
    by_id = {r["id"]: r for r in source}
    if len(by_id) != len(source) or len({r["id"] for r in predictions}) != len(predictions):
        raise ValueError("Repeated source or prediction IDs")
    if {r["id"] for r in predictions} != set(by_id):
        raise ValueError("Source and prediction cohorts differ")
    diagnostics = []
    for stored in predictions:
        row = by_id[stored["id"]]
        if stored["text"] != row["text"]:
            raise ValueError(f"Prediction/source text differs: {row['id']}")
        matches = [{"start": m.start(), "end": m.end(), "text": m.group()} for m in pattern.finditer(row["text"])]
        matched, gate = bool(matches), rule.category in row["source_labels"]
        diagnostics.append({"id": row["id"], "stored_ungated": stored["regex_sale_flag"],
                            "stored_gated": stored["source_category_gated_regex_sale_flag"],
                            "recomputed_ungated": matched, "recomputed_gated": matched and gate,
                            "source_category_gate": gate, "matched_spans": matches,
                            "stored_flags_agree": stored["regex_sale_flag"] is matched
                            and stored["source_category_gated_regex_sale_flag"] is (matched and gate)})
    controls = [{"text": text, "expected": expected, "actual": bool(pattern.search(text)), "reason": reason}
                for text, expected, reason in CONTROLS]
    report = {"rule_id": rule.id, "pattern": pattern.pattern, "category": rule.category,
              "prediction_sha256": digest(prediction_path), "source_sha256": digest(source_path),
              "records": len(diagnostics), "ungated_matches": sum(r["recomputed_ungated"] for r in diagnostics),
              "gated_matches": sum(r["recomputed_gated"] for r in diagnostics),
              "stored_flag_mismatches": sum(not r["stored_flags_agree"] for r in diagnostics),
              "controls_passed": all(r["expected"] == r["actual"] for r in controls),
              "controls": controls, "records_detail": diagnostics,
              "interpretation": "These are legacy affirmative-sale risk flags, not sale-mention or polarity predictions. Denials should not trigger them. Quoted rental, coordinated verbs, passive voice and named company subjects are outside this narrow pattern. Agreement verifies its application, not its adequacy as a competitive regex baseline.",
              "test_exposure": "Post-test diagnostic only. The regex, TF-IDF model and frozen predictions have not been changed or tuned."}
    out.mkdir(parents=True)
    (out / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Legacy sale-regex diagnostic", "",
             f"Checked {report['records']} source records by ID and exact paragraph text. Recomputed matches: {report['ungated_matches']} ungated, {report['gated_matches']} category-gated. Stored-flag mismatches: {report['stored_flag_mismatches']}.", "",
             "## Exact pattern", "", "```regex", pattern.pattern, "```", "",
             report["interpretation"], "", "## Synthetic controls", "",
             "| Text | Expected risk flag | Actual |", "| --- | --- | --- |"]
    lines += [f"| {r['text']} | {r['expected']} | {r['actual']} |" for r in controls]
    lines += ["", "A false flag does not mean no sale-related language exists. Denials are intentionally excluded; rental/list wording and richer affirmative/conditional phrasing can be missed. The original zero-match result is reproducible, but this legacy rule is a weak comparator for general practice/polarity detection.", "",
              "Future baselines should distinguish mention detection from permitted/denied/conditional classification, cover declared actions and evidence formats, and be developed using training/validation examples before a separate held-out evaluation.", "", report["test_exposure"], ""]
    (out / "REPORT.md").write_text("\n".join(lines))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit_regex(args.predictions, args.source, args.out)
    print(json.dumps({k: report[k] for k in ("records", "ungated_matches", "gated_matches", "stored_flag_mismatches", "controls_passed")}, indent=2))
    if report["stored_flag_mismatches"] or not report["controls_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
