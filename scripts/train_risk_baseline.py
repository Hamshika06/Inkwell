"""Fit actor-aware TF-IDF classifiers on covered risk-review targets only.

python -m scripts.train_risk_baseline --out runs/risk-actor-masked-tfidf-seed42
"""
import argparse
import json
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np
import sklearn
from sklearn.metrics.pairwise import cosine_similarity

from inkwell.common import ROOT, key
from inkwell.risk_baseline import ActorMaskedPredictor, coverage_targets, evaluate_masked, target_triples
from scripts.sale_review import digest, read_rows

SCHEMA = ROOT / "configs/risk_baseline_schema.json"


def validate_split(rows, originals, split, schema, default_review):
    issues, seen = [], set()
    for n, row in enumerate(rows, 1):
        prefix = f"{split} line {n}"
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            issues.append(prefix + ": record with string id required")
            continue
        identifier = row["id"]
        if identifier in seen:
            issues.append(prefix + ": repeated ID")
        seen.add(identifier)
        original = originals.get(identifier)
        if original is None or {k: v for k, v in row.items() if k != "risk_review"} != original:
            issues.append(prefix + ": source fields changed or unknown ID")
            continue
        if row["split"] != split:
            issues.append(prefix + ": wrong split")
        review = row.get("risk_review")
        if not isinstance(review, dict):
            issues.append(prefix + ": risk_review object required")
            continue
        if set(review) != set(default_review):
            issues.append(prefix + ": unknown/missing review fields; update the schema explicitly")
        if review.get("status") == "unannotated":
            if review != default_review:
                issues.append(prefix + ": unannotated record contains changed review fields")
            continue
        if review.get("status") != "annotated":
            issues.append(prefix + ": unknown annotation status")
            continue
        coverage, practices = review.get("covered_practice_types"), review.get("practices")
        if not isinstance(coverage, list) or any(not isinstance(v, str) for v in coverage):
            issues.append(prefix + ": coverage must be a string list")
            continue
        if not coverage or len(coverage) != len(set(coverage)) or set(coverage) - set(schema["practice_types"]):
            issues.append(prefix + ": invalid or empty practice coverage")
        if not isinstance(practices, list):
            issues.append(prefix + ": practices must be a list")
            continue
        if not isinstance(review.get("notes"), str):
            issues.append(prefix + ": record notes must be a string")
        elif not practices and not review["notes"].strip():
            issues.append(prefix + ": checked-negative record needs explanatory notes")
        if (review.get("annotation_origin") not in ("manual", "model_assisted", "imported")
                or not isinstance(review.get("author_id"), str) or not review["author_id"].strip()):
            issues.append(prefix + ": annotation provenance missing")
        for j, practice in enumerate(practices):
            where = f"{prefix}, practice {j}"
            if not isinstance(practice, dict):
                issues.append(where + ": practice object required")
                continue
            for field, values in [("practice_type", schema["practice_types"]), ("actor", schema["actors"]), ("label", schema["labels"])]:
                if not isinstance(practice.get(field), str) or practice[field] not in values:
                    issues.append(where + f": invalid {field}")
            if practice.get("practice_type") not in coverage:
                issues.append(where + ": practice is outside explicit coverage")
            if practice.get("label") == "conditional" and not (practice.get("conditions") or practice.get("exceptions")):
                issues.append(where + ": conditional requires condition/exception evidence")
            if not isinstance(practice.get("notes"), str) or (practice.get("label") == "unclear" and not practice["notes"].strip()):
                issues.append(where + ": practice notes missing or unclear is unexplained")
            if "recipient" in practice:
                recipients = practice["recipient"]
                if not isinstance(recipients, list) or any(not isinstance(v, str) or not v.strip() for v in recipients):
                    issues.append(where + ": recipient roles must be nonempty strings in a list")
                elif len(recipients) != len(set(recipients)):
                    issues.append(where + ": recipient roles must be distinct")
            for field in schema["span_fields"] + [f for f in schema["optional_span_fields"] if f in practice]:
                spans = practice.get(field)
                if not isinstance(spans, list) or (field == "evidence" and not spans):
                    issues.append(where + f": invalid {field} span list")
                    continue
                for span in spans:
                    if not isinstance(span, dict):
                        issues.append(where + f": invalid {field} span object")
                        continue
                    a, b = span.get("start"), span.get("end")
                    if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(row["text"]) or row["text"][a:b] != span.get("text"):
                        issues.append(where + f": {field} span does not match source offsets")
    expected = {r["id"] for r in originals.values() if r["split"] == split}
    if seen != expected:
        issues.append(f"{split}: incomplete or unexpected source split IDs")
    if issues:
        raise ValueError("\n".join(issues[:15]) + f"\n({len(issues)} issue(s))")


def load_development_data(batch, schema):
    template_manifest = json.loads((batch / "review_manifest.json").read_text())
    if digest(batch / "combined_classifier.jsonl") != template_manifest["source_sha256"]:
        raise ValueError("Combined source checksum mismatch")
    originals = {r["id"]: r for r in read_rows(batch / "combined_classifier.jsonl")}
    # Read risk annotations from train and validation only; never read test.jsonl.
    train, validation = read_rows(batch / "train.jsonl"), read_rows(batch / "validation.jsonl")
    for split, rows in [("train", train), ("validation", validation)]:
        validate_split(rows, originals, split, schema, template_manifest["default_risk_review"])
    for field in ("id", "doc_id", "group_id"):
        if {r[field] for r in train} & {r[field] for r in validation}:
            raise ValueError(f"Train/validation {field} overlap")
    if {key(r["text"]) for r in train} & {key(r["text"]) for r in validation}:
        raise ValueError("Train/validation normalized-text overlap")
    return train, validation


def triple_list(triples, flags):
    return [list(t) for t, flag in zip(triples, flags) if flag]


def train_run(batch, out, seed=42):
    if out.exists():
        raise ValueError("Run exists; choose a new output directory")
    schema = json.loads(SCHEMA.read_text())
    train, validation = load_development_data(batch, schema)
    triples = target_triples(schema)
    y_train, m_train = coverage_targets(train, triples)
    y_val_all, m_val_all = coverage_targets(validation, triples)
    included = m_train.any(axis=1)
    val_included = m_val_all.any(axis=1)
    if not val_included.any():
        raise ValueError("No known validation risk targets; annotate validation before evaluation")
    train_active = [r for r, keep in zip(train, included) if keep]
    val_active = [r for r, keep in zip(validation, val_included) if keep]
    y_val, m_val = y_val_all[val_included], m_val_all[val_included]
    model = ActorMaskedPredictor(triples, seed)
    start = time.perf_counter()
    model.fit([r["text"] for r in train], y_train, m_train)
    training_seconds = time.perf_counter() - start
    scores = model.scores([r["text"] for r in val_active])
    predicted = (np.isfinite(scores) & (scores >= 0)).astype(int)
    metrics = evaluate_masked(y_val, predicted, m_val, triples)
    metrics["population"] = {"validation_records": len(validation), "scored_annotated_records": len(val_active),
                              "unscored_unknown_records": len(validation) - len(val_active)}
    metrics["known_cells_with_finite_model_scores"] = int((m_val.astype(bool) & np.isfinite(scores)).sum())
    # Diagnostic only: the threshold is fixed and is not selected on validation.
    similarities = cosine_similarity(model.vectorizer.transform([r["text"] for r in val_active]),
                                     model.vectorizer.transform([r["text"] for r in train_active]))
    closest, maximum = similarities.argmax(axis=1), similarities.max(axis=1)
    metrics["template_overlap"] = {"threshold": .90, "annotated_validation_at_or_above_threshold": int((maximum >= .90).sum()),
                                   "below_threshold": evaluate_masked(y_val[maximum < .90], predicted[maximum < .90], m_val[maximum < .90], triples)}
    records = []
    for i, row in enumerate(val_active):
        records.append({"id": row["id"], "source": row["source"], "group_id": row["group_id"], "text": row["text"],
                        "gold_positive_triples": triple_list(triples, y_val[i]),
                        "predicted_triples": triple_list(triples, predicted[i]),
                        "predicted_on_known_targets": triple_list(triples, predicted[i] & m_val[i]),
                        "target_values": y_val[i].tolist(), "target_mask": m_val[i].tolist(),
                        "scores": [round(float(s), 6) if np.isfinite(s) else None for s in scores[i]],
                        "nearest_train_id": train_active[int(closest[i])]["id"], "nearest_train_cosine": float(maximum[i])})
    metadata = {
        "kind": "actor_aware_coverage_masked_tfidf_svm", "seed": seed, "schema_version": schema["version"],
        "schema_sha256": digest(SCHEMA), "source_sha256": digest(batch / "combined_classifier.jsonl"),
        "train_sha256": digest(batch / "train.jsonl"), "validation_sha256": digest(batch / "validation.jsonl"),
        "train_records": len(train), "train_used": len(train_active), "train_excluded_unknown": len(train) - len(train_active),
        "validation_records": len(validation), "validation_scored": len(val_active), "validation_excluded_unknown": len(validation) - len(val_active),
        "train_known_cells": int(m_train.sum()), "train_unknown_cells": int(m_train.size - m_train.sum()),
        "train_annotated_propositions": sum(len(r["risk_review"]["practices"]) for r in train_active),
        "train_positive_target_assignments": int(y_train.sum()),
        "train_authors": dict(Counter(r["risk_review"]["author_id"] for r in train_active)),
        "validation_authors": dict(Counter(r["risk_review"]["author_id"] for r in val_active)),
        "target_support": {"/".join(t): support for t, support in zip(triples, model.training_support)},
        "features": {"ngram_range": [1, 2], "min_df": 1, "max_features": 20000, "sublinear_tf": True,
                     "fitted_on": "Training rows with at least one known risk target only", "vocabulary_size": len(model.vectorizer.vocabulary_)},
        "classifier": {"C": 1.0, "class_weight": "balanced", "threshold": 0.0, "threshold_tuning": False},
        "implementation_sha256": {"inkwell/risk_baseline.py": digest(ROOT / "inkwell/risk_baseline.py"),
                                  "scripts/train_risk_baseline.py": digest(Path(__file__))},
        "training_seconds": training_seconds, "python": platform.python_version(), "sklearn": sklearn.__version__,
        "input_contract": schema["input"], "coverage_contract": schema["coverage_contract"],
        "score_contract": "Learned outputs are uncalibrated margins. Single-class labels use constant +/-1 sentinels. Labels with no known training cells have null scores and no positive prediction; unavailable predictions still count as misses on known validation positives.",
        "test_annotations_read": False, "test_evaluation_performed": False, "risk_score_integration": False,
        "limitations": ["Agreement with supplied model-assisted annotations, not calibrated privacy-risk accuracy.",
                        "Small, keyword-selected annotation subset with sparse actor/practice combinations.",
                        "Unannotated rows are excluded; partial actor supervision is conservative and does not assume every unlisted actor is negative.",
                        "Recall cannot be measured for any practice/actor/polarity target with zero known validation positives; see the support counts.",
                        "Predictions are paragraph-level label sets, without extracted scope or evidence spans.",
                        "Source-prefixed group separation is checked, but independent cross-source company/template isolation is not established."]}
    out.mkdir(parents=True)
    model.save(out / "model.joblib")
    metadata["model_sha256"] = digest(out / "model.joblib")
    for name, value in [("run.json", metadata), ("labels.json", [list(t) for t in triples]), ("validation_metrics.json", metrics), ("annotation_schema.json", schema)]:
        (out / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    (out / "validation_predictions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in records))
    write_report(out, metadata, metrics)
    return metadata, metrics


def write_report(out, run, metrics):
    def fmt(value):
        return "N/A" if value is None else f"{value:.3f}"
    joint = metrics["joint"]
    lines = ["# Actor-aware, coverage-masked TF-IDF baseline", "",
             f"Used {run['train_used']} training paragraphs; excluded {run['train_excluded_unknown']} wholly unknown paragraphs. Scored {run['validation_scored']} annotated validation paragraphs; excluded {run['validation_excluded_unknown']} unknown paragraphs.", "",
             "Word TF-IDF unigrams/bigrams and balanced binary LinearSVC models predict practice/actor/polarity triples. Vocabulary is fitted only on supervised training rows, and each classifier fits only its known target cells. Thresholds are fixed at zero. No test annotations were read and no test evaluation was performed.", "",
             "## Masking contract", ""]
    lines.extend("- " + rule for rule in run["coverage_contract"])
    lines += ["", "## Validation", "", "| Measure | Result |", "| --- | ---: |",
              f"| Joint masked micro F1 | {fmt(joint['micro_f1'])} |",
              f"| Macro F1 over known supported targets | {fmt(joint['macro_f1_supported'])} |",
              f"| Exact match on known targets | {fmt(joint['masked_exact_match'])} |",
              f"| Validation known target cells | {joint['known_cells']} |",
              f"| Validation unknown target cells | {joint['unknown_cells']} |", "",
              "## Practice results (actors retained)", "", "| Practice | Known positive support | Micro F1 | Supported-target macro F1 |",
              "| --- | ---: | ---: | ---: |"]
    for practice, m in metrics["by_practice"].items():
        support = sum(r["positive_support"] for r in m["per_target"].values())
        lines.append(f"| {practice} | {support} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} |")
    flag = metrics["first_party_sale_flag"]["per_target"]["first_party_sale_permitted_or_conditional"]
    lines += ["", "## First-party sale flags", "",
              "The flag combines first_party sale/permitted and sale/conditional only. Vendor restrictions and other actors are not collapsed into first-party labels.", "",
              f"Known paragraphs: {flag['known']}; unknown: {flag['unknown']}. TP={flag['tp']}, FP={flag['fp']}, FN={flag['fn']}, TN={flag['tn']}.",
              f"Precision={fmt(flag['precision'])}, recall={fmt(flag['recall'])}, F1={fmt(flag['f1'])}.", "",
              "## Interpretation", "",
              "All confusion counts and metrics exclude unknown ground-truth cells. Exact match considers only known cells on each scored row; it is not a claim of exact recovery of every actor/scope in the paragraph. Each target's confusion matrix is [[TN, FP], [FN, TP]]. Recall is null without known positive support.", "",
              f"{metrics['template_overlap']['annotated_validation_at_or_above_threshold']} annotated validation paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a supervised training paragraph. See validation_predictions.jsonl for nearest templates and all known/unknown targets.", ""]
    lines.extend("- " + limitation for limitation in run["limitations"])
    lines += ["", "This run changes neither annotations nor the live risk-score engine. Scores are not probabilities, and an empty prediction is not a safety judgment.", ""]
    (out / "REPORT.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/review/sale-v2")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run, metrics = train_run(args.batch, args.out, args.seed)
    print(json.dumps({"run": str(args.out), "train_used": run["train_used"], "train_excluded_unknown": run["train_excluded_unknown"],
                      "validation_scored": run["validation_scored"], "joint_micro_f1": metrics["joint"]["micro_f1"],
                      "masked_exact_match": metrics["joint"]["masked_exact_match"], "first_party_sale_flag": metrics["first_party_sale_flag"]["per_target"]}, indent=2))


if __name__ == "__main__":
    main()
