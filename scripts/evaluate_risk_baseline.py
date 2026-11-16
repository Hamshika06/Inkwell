"""Evaluate a frozen actor-aware baseline on known test targets only.

python -m scripts.evaluate_risk_baseline --run runs/risk-actor-masked-tfidf-seed42 --out runs/risk-actor-masked-tfidf-seed42/test-masked-v1
"""
import argparse
import json
from pathlib import Path

import numpy as np
import sklearn
from sklearn.metrics.pairwise import cosine_similarity

from inkwell.common import ROOT, key
from inkwell.risk_baseline import ActorMaskedPredictor, coverage_targets, evaluate_masked, target_triples
from scripts.sale_review import digest, read_rows
from scripts.train_risk_baseline import load_development_data, triple_list, validate_split


def evaluate_run(run, batch, out):
    if out.exists():
        raise ValueError("Evaluation exists; preserve it and choose a new output directory")
    metadata = json.loads((run / "run.json").read_text())
    schema_source = ROOT / "configs/risk_baseline_schema.json"
    schema_snapshot = run / "annotation_schema.json"
    protected = {
        run / "model.joblib": metadata["model_sha256"],
        schema_source: metadata["schema_sha256"],
        batch / "combined_classifier.jsonl": metadata["source_sha256"],
        batch / "train.jsonl": metadata["train_sha256"],
        batch / "validation.jsonl": metadata["validation_sha256"],
    }
    protected.update({ROOT / path: value for path, value in metadata["implementation_sha256"].items()})
    for path, expected in protected.items():
        if digest(path) != expected:
            raise ValueError(f"Frozen input/model/implementation checksum mismatch: {path}")
    if metadata["sklearn"] != sklearn.__version__:
        raise ValueError("Use the scikit-learn version recorded in the saved run")
    if metadata["classifier"]["threshold"] != 0.0:
        raise ValueError("This evaluator requires the saved baseline's zero threshold")
    training_run_hash = digest(run / "run.json")
    # Training hashed the source schema, but serialized the snapshot with indentation.
    # Verify the source bytes and snapshot contents separately; do not rewrite either.
    protected[schema_snapshot] = digest(schema_snapshot)
    schema = json.loads(schema_snapshot.read_text())
    if schema != json.loads(schema_source.read_text()):
        raise ValueError("Saved schema contents differ from the verified training schema")
    train, validation = load_development_data(batch, schema)
    originals = {r["id"]: r for r in read_rows(batch / "combined_classifier.jsonl")}
    template = json.loads((batch / "review_manifest.json").read_text())
    test_path = batch / "test.jsonl"
    test_hash = digest(test_path)
    test = read_rows(test_path)
    validate_split(test, originals, "test", schema, template["default_risk_review"])
    for field in ("id", "doc_id", "group_id"):
        if {r[field] for r in test} & {r[field] for r in train + validation}:
            raise ValueError(f"Test/development {field} overlap")
    if {key(r["text"]) for r in test} & {key(r["text"]) for r in train + validation}:
        raise ValueError("Test/development normalized-text overlap")
    triples = target_triples(schema)
    if json.loads((run / "labels.json").read_text()) != [list(t) for t in triples]:
        raise ValueError("Saved target order differs from the frozen schema")
    model = ActorMaskedPredictor.load(run / "model.joblib")
    if model.triples != triples:
        raise ValueError("Saved model target order differs from the frozen schema")
    y_all, mask_all = coverage_targets(test, triples)
    included = mask_all.any(axis=1)
    if not included.any():
        raise ValueError("No known test risk targets; nothing to evaluate")
    active = [r for r, keep in zip(test, included) if keep]
    y, mask = y_all[included], mask_all[included]
    scores = model.scores([r["text"] for r in active])
    predicted = (np.isfinite(scores) & (scores >= metadata["classifier"]["threshold"])).astype(int)
    metrics = evaluate_masked(y, predicted, mask, triples)
    metrics["population"] = {"test_records": len(test), "scored_annotated_records": len(active),
                              "excluded_unknown_records": len(test) - len(active)}
    metrics["known_cells_with_finite_model_scores"] = int((mask.astype(bool) & np.isfinite(scores)).sum())
    # Previously exposed clause IDs are separated, without claiming policy independence.
    exposed_ids = set(template.get("previously_evaluated_test_ids", []))
    exposed = np.array([r["id"] in exposed_ids for r in active], dtype=bool)
    metrics["prior_sale_v1_clause_exposure"] = {
        "previously_evaluated_ids": evaluate_masked(y[exposed], predicted[exposed], mask[exposed], triples),
        "other_annotated_ids": evaluate_masked(y[~exposed], predicted[~exposed], mask[~exposed], triples),
        "contract": "ID-level diagnostic only; other IDs are not guaranteed to be independent policies or templates.",
    }
    metrics["by_source"] = {}
    for source in sorted({r["source"] for r in active}):
        subset = np.array([r["source"] == source for r in active])
        metrics["by_source"][source] = evaluate_masked(y[subset], predicted[subset], mask[subset], triples)
    _, train_mask = coverage_targets(train, triples)
    train_active = [r for r, keep in zip(train, train_mask.any(axis=1)) if keep]
    similarity = cosine_similarity(model.vectorizer.transform([r["text"] for r in active]),
                                   model.vectorizer.transform([r["text"] for r in train_active]))
    nearest, maximum = similarity.argmax(axis=1), similarity.max(axis=1)
    metrics["template_overlap"] = {"threshold": .90, "annotated_test_at_or_above_threshold": int((maximum >= .90).sum()),
                                   "below_threshold": evaluate_masked(y[maximum < .90], predicted[maximum < .90], mask[maximum < .90], triples)}
    records = []
    for i, row in enumerate(active):
        records.append({"id": row["id"], "source": row["source"], "group_id": row["group_id"], "text": row["text"],
                        "previously_evaluated_in_sale_v1": bool(exposed[i]),
                        "gold_positive_triples": triple_list(triples, y[i]),
                        "predicted_triples": triple_list(triples, predicted[i]),
                        "predicted_on_known_targets": triple_list(triples, predicted[i] & mask[i]),
                        "target_values": y[i].tolist(), "target_mask": mask[i].tolist(),
                        "scores": [round(float(s), 6) if np.isfinite(s) else None for s in scores[i]],
                        "nearest_train_id": train_active[int(nearest[i])]["id"], "nearest_train_cosine": float(maximum[i])})
    evaluation = {
        "kind": "frozen_actor_aware_masked_test_evaluation", "schema_version": schema["version"],
        "model_sha256": metadata["model_sha256"], "training_run_sha256": training_run_hash,
        "schema_sha256": metadata["schema_sha256"], "source_sha256": metadata["source_sha256"],
        "saved_schema_sha256": protected[schema_snapshot],
        "train_sha256": metadata["train_sha256"], "validation_sha256": metadata["validation_sha256"],
        "test_sha256": test_hash, "review_manifest_sha256": digest(batch / "review_manifest.json"),
        "evaluator_sha256": digest(Path(__file__)), "sklearn": sklearn.__version__,
        "test_records": len(test), "test_scored": len(active), "test_excluded_unknown": len(test) - len(active),
        "annotated_ids": [r["id"] for r in active], "previously_evaluated_clause_ids": [r["id"] for r, yes in zip(active, exposed) if yes],
        "threshold": metadata["classifier"]["threshold"], "retrained": False, "threshold_tuning": False,
        "coverage_contract": metadata["coverage_contract"],
        "contract": "Frozen-model test evaluation on annotated, covered risk targets only. Unknown targets and wholly unannotated paragraphs are excluded from metrics. Results measure agreement with supplied annotations and do not establish calibrated privacy-risk accuracy.",
    }
    # Reject any concurrent input/model edits instead of saving mixed-version results.
    for path, expected in list(protected.items()) + [(test_path, test_hash), (run / "run.json", training_run_hash)]:
        if digest(path) != expected:
            raise ValueError(f"Protected evaluation input changed: {path}")
    out.mkdir(parents=True)
    for name, value in [("evaluation.json", evaluation), ("test_metrics.json", metrics)]:
        (out / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    (out / "test_predictions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in records))
    write_report(out, evaluation, metrics)
    return evaluation, metrics


def write_report(out, run, metrics):
    def fmt(value):
        return "N/A" if value is None else f"{value:.3f}"
    joint = metrics["joint"]
    lines = ["# Frozen actor-aware, coverage-masked test evaluation", "",
             f"Scored {run['test_scored']} annotated paragraphs from the {run['test_records']}-record test split. Excluded {run['test_excluded_unknown']} wholly unannotated paragraphs. These are not metrics over the entire test population.", "",
             "The saved TF-IDF vocabulary, classifiers, target order, coverage masks and zero thresholds were frozen. No fitting, retraining or threshold tuning was performed. The original trained model and training-run metadata remain unchanged.", "",
             "## Masked test results", "", "| Measure | Result |", "| --- | ---: |",
             f"| Joint masked micro F1 | {fmt(joint['micro_f1'])} |",
             f"| Supported-target macro F1 | {fmt(joint['macro_f1_supported'])} |",
             f"| Exact match on known targets | {fmt(joint['masked_exact_match'])} |",
             f"| Known target cells | {joint['known_cells']} |",
             f"| Unknown target cells (excluded) | {joint['unknown_cells']} |", "",
             "Exact match checks only known cells on rows with supervision, not every possible actor or scope. Each per-target confusion matrix is [[TN, FP], [FN, TP]]. Recall is undefined without known positive support.", "",
             "## Practice results, with actors retained", "",
             "| Practice | Known positive support | Micro F1 | Supported-target macro F1 |",
             "| --- | ---: | ---: | ---: |"]
    for practice, m in metrics["by_practice"].items():
        support = sum(r["positive_support"] for r in m["per_target"].values())
        lines.append(f"| {practice} | {support} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} |")
    sale = metrics["first_party_sale_flag"]["per_target"]["first_party_sale_permitted_or_conditional"]
    lines += ["", "## First-party sale flags", "",
              "The binary flag combines only sale/first_party/permitted and sale/first_party/conditional. Other actors' denials are not first-party negatives.", "",
              f"Known paragraphs={sale['known']}; actor-unknown paragraphs excluded={sale['unknown']}. TP={sale['tp']}, FP={sale['fp']}, FN={sale['fn']}, TN={sale['tn']}.",
              f"Precision={fmt(sale['precision'])}, recall={fmt(sale['recall'])}, F1={fmt(sale['f1'])}.", "",
              "## Prior clause exposure", "",
              "| Test subset | Scored paragraphs | Masked micro F1 |", "| --- | ---: | ---: |"]
    exposure = metrics["prior_sale_v1_clause_exposure"]
    for label, field in [("Previously evaluated in sale-v1", "previously_evaluated_ids"), ("Other annotated clause IDs", "other_annotated_ids")]:
        m = exposure[field]["joint"]
        lines.append(f"| {label} | {m['records']} | {fmt(m['micro_f1'])} |")
    lines += ["", "Other clause IDs are not necessarily independent companies or templates. Source-prefixed policy/group and exact normalized-text separation from train/validation were checked; broader company independence is not established.", "",
              f"{metrics['template_overlap']['annotated_test_at_or_above_threshold']} scored paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a supervised training paragraph. The below-threshold diagnostic is in test_metrics.json.", "",
              "## Limits", "",
              "- The annotated test subset is small and selected; results measure agreement with supplied model-assisted annotations.",
              "- Unknown cells remain excluded. Scores and single-class sentinels are not probabilities; an empty prediction does not mean safe.",
              "- Predictions are paragraph-level triples, without extracted evidence spans or resolved scope.",
              "- Keep this as the final measurement of this frozen model; later model changes require a separate evaluation protocol.", "",
              "Files: evaluation.json (input/model hashes and cohort), test_metrics.json (masked confusion counts and subgroup results), test_predictions.jsonl (labels, masks, scores and individual predictions). No live risk-score integration was performed.", ""]
    (out / "REPORT.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/review/sale-v2")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run, metrics = evaluate_run(args.run, args.batch, args.out)
    print(json.dumps({"scored": run["test_scored"], "excluded_unknown": run["test_excluded_unknown"],
                      "masked_micro_f1": metrics["joint"]["micro_f1"], "masked_exact_match": metrics["joint"]["masked_exact_match"],
                      "first_party_sale_flag": metrics["first_party_sale_flag"]["per_target"]}, indent=2))


if __name__ == "__main__":
    main()
