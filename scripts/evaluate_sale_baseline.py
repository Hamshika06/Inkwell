"""Evaluate the saved sale model on a declared test cohort, without fitting.

python -m scripts.evaluate_sale_baseline --run runs/sale-tfidf-seed42 --out runs/sale-tfidf-seed42/test-26-v1
"""
import argparse
import json
from pathlib import Path

import numpy as np
import sklearn
from sklearn.metrics.pairwise import cosine_similarity

from inkwell.common import ROOT, key
from inkwell.risk import COMPILED
from inkwell.sale import SalePredictor, label_pairs, multilabel_metrics, targets
from scripts.sale_review import digest, load_batch, read_rows, review_issues
from scripts.train_sale_baseline import evaluation


def load_test_data(batch, test_path, train_path, validation_path, cohort_path, run):
    metadata = json.loads((run / "run.json").read_text())
    schema_path = run / "annotation_schema.json"
    for path, expected in [(run / "model.joblib", metadata["model_sha256"]),
                           (schema_path, metadata["schema_sha256"]),
                           (train_path, metadata["train_sha256"]),
                           (validation_path, metadata["validation_sha256"]),
                           (batch / "candidates.jsonl", metadata["candidate_sha256"])]:
        if digest(path) != expected:
            raise ValueError(f"Saved run input/model checksum mismatch: {path}")
    if metadata["sklearn"] != sklearn.__version__:
        raise ValueError("Use the scikit-learn version recorded in the saved run")
    if metadata["classifier"]["threshold"] != 0.0:
        raise ValueError("Evaluator supports the saved baseline's fixed zero threshold only")
    schema = json.loads(schema_path.read_text())
    _, originals = load_batch(batch)
    original_ids = {identifier for identifier, row in originals.items() if row["split"] == "test"}
    cohort = json.loads(cohort_path.read_text())
    selected, excluded = cohort["selected_ids"], cohort["excluded_ids"]
    if (cohort.get("split") != "test" or len(selected) != len(set(selected))
            or len(excluded) != len(set(excluded)) or set(selected) & set(excluded)
            or set(selected) | set(excluded) != original_ids
            or cohort["records"] != len(selected) or cohort["original_source_records"] != len(original_ids)
            or cohort["source_candidate_sha256"] != metadata["candidate_sha256"]):
        raise ValueError("Invalid test cohort definition or source snapshot")
    rows = read_rows(test_path)
    if any(row.get("split") != "test" for row in rows):
        raise ValueError("Evaluation input must contain test records only")
    issues = review_issues(list(enumerate(rows, 1)), originals, schema, require_adjudication=False)
    if issues:
        raise ValueError(f"Test annotation issue: {issues[0]}")
    if {row["id"] for row in rows} != set(selected):
        raise ValueError("Test records do not exactly match the declared cohort")
    if digest(test_path) != cohort["initial_annotation_sha256"]:
        raise ValueError("Test annotations changed after the cohort was declared")
    train, validation = read_rows(train_path), read_rows(validation_path)
    for field in ("id", "doc_id", "group_id"):
        if {row[field] for row in rows} & {row[field] for row in train + validation}:
            raise ValueError(f"Test/train-validation overlap: {field}")
    if {key(row["text"]) for row in rows} & {key(row["text"]) for row in train + validation}:
        raise ValueError("Test/train-validation normalized-text overlap")
    return metadata, schema, cohort, rows, train


def evaluate_test(run, batch, test_path, train_path, validation_path, cohort_path, out):
    if out.exists():
        raise ValueError("Test result exists; preserve it and choose a new output directory")
    metadata, schema, cohort, rows, train = load_test_data(batch, test_path, train_path, validation_path, cohort_path, run)
    model = SalePredictor.load(run / "model.joblib")
    pairs = label_pairs(schema)
    if model.pairs != pairs or json.loads((run / "labels.json").read_text()) != [list(p) for p in pairs]:
        raise ValueError("Saved model label order differs from the frozen schema")
    texts = [row["text"] for row in rows]
    scores = model.scores(texts)
    predicted = (scores >= metadata["classifier"]["threshold"]).astype(int)
    y = targets(rows, pairs)
    metrics = evaluation(y, predicted, pairs)
    sale_columns = [i for i, pair in enumerate(pairs) if pair[0] == "sale" and pair[1] in ("permitted", "conditional")]
    truth = y[:, sale_columns].any(axis=1).astype(int)[:, None]
    rule, pattern = next((r, p) for r, p in COMPILED if r.id == "data_sale")
    regex = np.array([bool(pattern.search(row["text"])) for row in rows], dtype=int)[:, None]
    gated = np.array([bool(pattern.search(row["text"])) and rule.category in row["source_labels"] for row in rows], dtype=int)[:, None]
    metrics["regex_comparison"] = {
        "ungated": multilabel_metrics(truth, regex, ["sale_permitted_or_conditional"]),
        "source_category_gated": multilabel_metrics(truth, gated, ["sale_permitted_or_conditional"]),
        "pattern": pattern.pattern,
    }
    similarity = cosine_similarity(model.vectorizer.transform(texts), model.vectorizer.transform([row["text"] for row in train]))
    nearest, maximum = similarity.argmax(axis=1), similarity.max(axis=1)
    metrics["template_overlap"] = {"threshold": .90, "test_records_at_or_above_threshold": int((maximum >= .90).sum())}
    metrics["test_below_template_threshold"] = evaluation(y[maximum < .90], predicted[maximum < .90], pairs)
    predictions = []
    for i, row in enumerate(rows):
        predictions.append({"id": row["id"], "group_id": row["group_id"], "text": row["text"],
                            "gold_pairs": [list(p) for p, hit in zip(pairs, y[i]) if hit],
                            "predicted_pairs": [list(p) for p, hit in zip(pairs, predicted[i]) if hit],
                            "margins": {"/".join(p): round(float(s), 6) for p, s in zip(pairs, scores[i])},
                            "regex_sale_flag": bool(regex[i, 0]), "source_category_gated_regex_sale_flag": bool(gated[i, 0]),
                            "nearest_train_id": train[int(nearest[i])]["id"], "nearest_train_cosine": float(maximum[i])})
    evaluation_run = {"kind": "frozen_sale_test_evaluation", "cohort_version": cohort["version"],
                      "test_records": len(rows), "original_source_test_records": cohort["original_source_records"],
                      "excluded_ids": cohort["excluded_ids"], "selection_reason": cohort["selection_reason"],
                      "test_sha256": digest(test_path), "cohort_sha256": digest(cohort_path),
                      "model_sha256": metadata["model_sha256"], "training_run_sha256": digest(run / "run.json"),
                      "schema_sha256": metadata["schema_sha256"], "train_sha256": metadata["train_sha256"],
                      "validation_sha256": metadata["validation_sha256"], "sklearn": sklearn.__version__,
                      "threshold": metadata["classifier"]["threshold"], "retrained": False, "threshold_tuning": False,
                      "contract": "Complete evaluation of the user-declared test cohort. Compare against supplied annotations; do not tune this frozen run on test results."}
    # Freeze check before writing results; evaluation must never mutate the model.
    if digest(run / "model.joblib") != metadata["model_sha256"]:
        raise ValueError("Model changed during evaluation")
    out.mkdir(parents=True)
    for name, value in [("test_metrics.json", metrics), ("evaluation.json", evaluation_run), ("test_cohort.json", cohort)]:
        (out / name).write_text(json.dumps(value, indent=2) + "\n")
    (out / "test_predictions.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions))
    write_report(out, evaluation_run, metrics)
    return evaluation_run, metrics


def write_report(out, run, metrics):
    def fmt(number):
        return "N/A" if number is None else f"{number:.3f}"
    lines = ["# Frozen TF-IDF test evaluation", "",
             f"Official cohort: **{run['cohort_version']}**, {run['test_records']} annotated paragraphs, selected from {run['original_source_test_records']} original source candidates before test predictions were computed.", "",
             run["selection_reason"], "",
             f"Excluded original ID: {', '.join(run['excluded_ids']) or 'None'}. The original candidate snapshot is retained for provenance. This report evaluates the declared cohort.", "",
             "The saved model, TF-IDF vocabulary, label order and zero thresholds were frozen. No fitting, retraining or threshold tuning was performed.", "",
             "## Results", "", "| Task | Micro F1 | Supported-label macro F1 | Exact label-set match |",
             "| --- | ---: | ---: | ---: |"]
    for task in ("joint", "practice_type"):
        m = metrics[task]
        lines.append(f"| {task} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} | {fmt(m['exact_match'])} |")
    lines += ["", "## First-party sale flags", "",
              "A positive flag means sale/permitted or sale/conditional in the reference annotation. Business transfers and other contextual practices do not count as ordinary first-party sale flags.", "",
              "| Method | Precision | Recall | F1 | TP | FP | FN | TN |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, method in [("TF-IDF", metrics["sale_flag"]), ("Regex (ungated)", metrics["regex_comparison"]["ungated"]),
                         ("Regex (source topic gated)", metrics["regex_comparison"]["source_category_gated"])]:
        r = method["per_label"]["sale_permitted_or_conditional"]
        lines.append(f"| {name} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {r['tp']} | {r['fp']} | {r['fn']} | {r['tn']} |")
    lines += ["", "## Polarity by practice type", "", "| Practice | Positive pair support | Micro F1 | Supported-label macro F1 |",
              "| --- | ---: | ---: | ---: |"]
    for practice, m in metrics["polarity_by_practice"].items():
        support = sum(r["support"] for r in m["per_label"].values())
        lines.append(f"| {practice} | {support} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} |")
    lines += ["", "## Limits", "",
              "- This is a small, keyword-selected test cohort; results measure agreement with the supplied annotations, not general privacy-risk accuracy.",
              "- Per-label confusion matrices use [[TN, FP], [FN, TP]]. Labels with zero support have null recall; supported-label macro F1 excludes them.",
              "- Predictions describe paragraph-level labels, not extracted evidence spans or resolved scopes.",
              f"- {metrics['template_overlap']['test_records_at_or_above_threshold']} test paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a training paragraph.",
              "- Keep these results as a final measurement of this saved model. Any subsequent model changes need a separate evaluation protocol.", "",
              "See test_predictions.jsonl for individual errors and margins, test_metrics.json for full metrics, and evaluation.json for input/model hashes.", ""]
    (out / "REPORT.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/review/sale-v1")
    parser.add_argument("--test", type=Path, default=ROOT / "data/review/sale-v1/test.jsonl")
    parser.add_argument("--train", type=Path, default=ROOT / "data/review/sale-v1/train.normalized.jsonl")
    parser.add_argument("--validation", type=Path, default=ROOT / "data/review/sale-v1/validation.jsonl")
    parser.add_argument("--cohort", type=Path, default=ROOT / "data/review/sale-v1/test_cohort.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run, metrics = evaluate_test(args.run, args.batch, args.test, args.train, args.validation, args.cohort, args.out)
    print(json.dumps({"test_records": run["test_records"], "joint_micro_f1": metrics["joint"]["micro_f1"],
                      "exact_match": metrics["joint"]["exact_match"], "sale_flag": metrics["sale_flag"]}, indent=2))


if __name__ == "__main__":
    main()
