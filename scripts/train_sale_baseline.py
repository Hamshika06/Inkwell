"""Train a paragraph-level practice/polarity baseline; evaluate validation only.

python -m scripts.train_sale_baseline --out runs/sale-tfidf-seed42
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
from inkwell.risk import COMPILED
from inkwell.sale import SalePredictor, label_pairs, multilabel_metrics, targets
from scripts.sale_review import SCHEMA, digest, load_batch, read_rows, review_issues


def load_training_data(batch, train_path, validation_path, schema):
    _, originals = load_batch(batch)
    splits = []
    for path, split in [(train_path, "train"), (validation_path, "validation")]:
        rows = read_rows(path)
        if any(r.get("split") != split for r in rows):
            raise ValueError(f"{path} must contain only {split} records")
        issues = review_issues(list(enumerate(rows, 1)), originals, schema, require_adjudication=False)
        if issues:
            raise ValueError(f"{path}: {issues[0]}")
        expected = {r["id"] for r in originals.values() if r["split"] == split}
        if {r["id"] for r in rows} != expected:
            raise ValueError(f"{path}: incomplete {split} candidate coverage")
        splits.append(rows)
    train, validation = splits
    for field in ("id", "doc_id", "group_id"):
        if {r[field] for r in train} & {r[field] for r in validation}:
            raise ValueError(f"Train/validation overlap: {field}")
    if {key(r["text"]) for r in train} & {key(r["text"]) for r in validation}:
        raise ValueError("Train/validation normalized-text overlap")
    return train, validation


def evaluation(y, predicted, pairs):
    result = {"joint": multilabel_metrics(y, predicted, ["/".join(p) for p in pairs]),
              "polarity_by_practice": {}}
    types = list(dict.fromkeys(p[0] for p in pairs))
    for practice in types:
        columns = [i for i, pair in enumerate(pairs) if pair[0] == practice]
        result["polarity_by_practice"][practice] = multilabel_metrics(
            y[:, columns], predicted[:, columns], [pairs[i][1] for i in columns])
    ty = np.column_stack([y[:, [i for i, p in enumerate(pairs) if p[0] == t]].any(axis=1) for t in types])
    tp = np.column_stack([predicted[:, [i for i, p in enumerate(pairs) if p[0] == t]].any(axis=1) for t in types])
    result["practice_type"] = multilabel_metrics(ty, tp, types)
    columns = [i for i, p in enumerate(pairs) if p[0] == "sale" and p[1] in ("permitted", "conditional")]
    sale_y = y[:, columns].any(axis=1).astype(int)[:, None]
    sale_pred = predicted[:, columns].any(axis=1).astype(int)[:, None]
    result["sale_flag"] = multilabel_metrics(sale_y, sale_pred, ["sale_permitted_or_conditional"])
    counts = result["sale_flag"]["per_label"]["sale_permitted_or_conditional"]
    result["sale_flag"]["false_positive_rate"] = counts["fp"] / (counts["fp"] + counts["tn"]) if counts["fp"] + counts["tn"] else None
    return result


def train_run(batch, train_path, validation_path, out, seed=42):
    if out.exists():
        raise ValueError("Run exists; choose a new output directory")
    schema = json.loads(SCHEMA.read_text())
    train, validation = load_training_data(batch, train_path, validation_path, schema)
    pairs = label_pairs(schema)
    y_train, y_val = targets(train, pairs), targets(validation, pairs)
    model = SalePredictor(pairs, seed)
    start = time.perf_counter()
    model.fit([r["text"] for r in train], y_train)
    seconds = time.perf_counter() - start
    texts = [r["text"] for r in validation]
    scores = model.scores(texts)
    predicted = (scores >= 0).astype(int)
    metrics = evaluation(y_val, predicted, pairs)
    sale_columns = [i for i, p in enumerate(pairs) if p[0] == "sale" and p[1] in ("permitted", "conditional")]
    truth_sale = y_val[:, sale_columns].any(axis=1).astype(int)[:, None]
    rule, pattern = next((r, p) for r, p in COMPILED if r.id == "data_sale")
    regex = np.array([bool(pattern.search(r["text"])) for r in validation], dtype=int)[:, None]
    gated = np.array([bool(pattern.search(r["text"])) and rule.category in r["source_labels"] for r in validation], dtype=int)[:, None]
    metrics["regex_comparison"] = {
        "contract": "Same binary sale-permitted-or-conditional target on full paragraphs. Regex does not predict polarity; missing matches are not safety judgments.",
        "ungated": multilabel_metrics(truth_sale, regex, ["sale_permitted_or_conditional"]),
        "source_category_gated": multilabel_metrics(truth_sale, gated, ["sale_permitted_or_conditional"]),
    }
    similarities = cosine_similarity(model.vectorizer.transform(texts), model.vectorizer.transform([r["text"] for r in train]))
    nearest = similarities.argmax(axis=1)
    maximum = similarities.max(axis=1)
    metrics["template_overlap"] = {
        "threshold": 0.90, "validation_records_at_or_above_threshold": int((maximum >= .90).sum()),
        "contract": "Train-fitted TF-IDF similarity diagnostic; repeated templates can overstate generalization.",
    }
    novel = maximum < .90
    metrics["validation_below_template_threshold"] = evaluation(y_val[novel], predicted[novel], pairs)
    records = []
    for i, row in enumerate(validation):
        records.append({"id": row["id"], "text": row["text"], "group_id": row["group_id"],
                        "gold_pairs": [list(p) for p, yes in zip(pairs, y_val[i]) if yes],
                        "predicted_pairs": [list(p) for p, yes in zip(pairs, predicted[i]) if yes],
                        "margins": {"/".join(p): round(float(s), 6) for p, s in zip(pairs, scores[i])},
                        "regex_sale_flag": bool(regex[i, 0]), "source_category_gated_regex_sale_flag": bool(gated[i, 0]),
                        "nearest_train_id": train[int(nearest[i])]["id"], "nearest_train_cosine": float(maximum[i])})
    metadata = {
        "kind": "sale_tfidf_linear_svm", "seed": seed, "schema_version": schema["version"],
        "train_sha256": digest(train_path), "validation_sha256": digest(validation_path), "schema_sha256": digest(SCHEMA),
        "candidate_sha256": digest(batch / "candidates.jsonl"), "train_records": len(train), "validation_records": len(validation),
        "train_propositions": sum(len(r["review"]["practices"]) for r in train),
        "validation_propositions": sum(len(r["review"]["practices"]) for r in validation),
        "train_target_assignments": int(y_train.sum()), "validation_target_assignments": int(y_val.sum()),
        "train_positive_support": {"/".join(p): int(y_train[:, i].sum()) for i, p in enumerate(pairs)},
        "training_authors": dict(Counter(r["review"]["reviewer"] for r in train)),
        "validation_authors": dict(Counter(r["review"]["reviewer"] for r in validation)),
        "training_seconds": seconds, "python": platform.python_version(), "sklearn": sklearn.__version__,
        "features": {"analyzer": "word", "ngram_range": [1, 2], "min_df": 1, "max_features": 20000, "sublinear_tf": True,
                     "fitted_vocabulary_size": len(model.vectorizer.vocabulary_)},
        "classifier": {"C": 1.0, "class_weight": "balanced", "threshold": 0.0, "threshold_tuning": False},
        "input": "Full paragraph text only. Annotation labels, evidence offsets, and source topic labels are not model features.",
        "target": "Multilabel paragraph-level practice/polarity pairs; opposing labels are retained, while repeated identical pairs collapse to one target.",
        "constant_labels": {"/".join(p): m for p, m in zip(pairs, model.models) if isinstance(m, int)},
        "limitations": ["Small keyword-selected candidate dataset; scores are not representative of all privacy clauses.",
                        "Reference annotations include AI-authored drafts; metrics measure agreement with these annotations.",
                        "No validation unclear examples; unsupported-label recall is undefined.",
                        "Model does not extract scoped propositions, conditions, exceptions or evidence spans; repeated identical pairs collapse to one label.",
                        "Pairs absent from training always predict negative; their -1 score is a constant sentinel, not a learned margin.",
                        "SVM margins are not calibrated probabilities; no deployment or risk-score integration is performed."],
        "test_evaluation_performed": False,
    }
    out.mkdir(parents=True)
    model.save(out / "model.joblib")
    metadata["model_sha256"] = digest(out / "model.joblib")
    for name, value in [("run.json", metadata), ("labels.json", [list(p) for p in pairs]), ("validation_metrics.json", metrics)]:
        (out / name).write_text(json.dumps(value, indent=2) + "\n")
    (out / "validation_predictions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    (out / "annotation_schema.json").write_text(SCHEMA.read_text())
    write_report(out, metadata, metrics)
    return metadata, metrics


def write_report(out, metadata, metrics):
    def fmt(value):
        return "N/A" if value is None else f"{value:.3f}"
    lines = ["# TF-IDF practice/polarity baseline", "",
             f"Training: {metadata['train_records']} paragraphs. Validation: {metadata['validation_records']} paragraphs. Seed: {metadata['seed']}.", "",
             "The vectorizer and models were fitted on training text only. Word unigrams/bigrams and balanced binary LinearSVC classifiers predict paragraph-level practice/polarity pairs. Thresholds are fixed at zero; there was no validation tuning or test evaluation.", "",
             "## Validation results", "", "| Task | Micro F1 | Macro F1 (supported labels) | Exact match |",
             "| --- | ---: | ---: | ---: |"]
    for task in ("joint", "practice_type"):
        m = metrics[task]
        lines.append(f"| {task} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} | {fmt(m['exact_match'])} |")
    lines += ["", "## Sale flag comparison", "", "A sale flag means permitted or conditional first-party personal-information sale. Contextual practices and denied/unclear statements are negative for this target.", "",
              "| Method | Precision | Recall | F1 | TP | FP | FN | TN |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    methods = {"TF-IDF": metrics["sale_flag"], "Regex (ungated)": metrics["regex_comparison"]["ungated"],
               "Regex (source topic gated)": metrics["regex_comparison"]["source_category_gated"]}
    for name, m in methods.items():
        r = m["per_label"]["sale_permitted_or_conditional"]
        lines.append(f"| {name} | {fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | {r['tp']} | {r['fp']} | {r['fn']} | {r['tn']} |")
    lines += ["", "## Polarity by practice type", "", "| Practice | Positive pair support | Micro F1 | Macro F1 (supported labels) |",
              "| --- | ---: | ---: | ---: |"]
    for practice, m in metrics["polarity_by_practice"].items():
        support = sum(r["support"] for r in m["per_label"].values())
        lines.append(f"| {practice} | {support} | {fmt(m['micro_f1'])} | {fmt(m['macro_f1_supported'])} |")
    overlap = metrics["template_overlap"]["validation_records_at_or_above_threshold"]
    novel = metrics["validation_below_template_threshold"]["joint"]
    lines += ["", "## Interpretation", "",
              f"{overlap} validation paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a training paragraph. Below that threshold, {novel['records']} paragraphs have joint micro F1 {fmt(novel['micro_f1'])}.", "",
              "Each label's confusion matrix in validation_metrics.json is [[TN, FP], [FN, TP]]. Recall is null when its reference support is zero. Macro F1 averages only labels with positive validation support; micro F1 also counts false predictions for unsupported labels.", ""]
    lines += [f"- {limitation}" for limitation in metadata["limitations"]]
    lines += ["", "Inspect validation_predictions.jsonl for every prediction, raw decision margin and nearest training template. No matching prediction is not a safety judgment.", ""]
    (out / "REPORT.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/review/sale-v1")
    parser.add_argument("--train", type=Path, default=ROOT / "data/review/sale-v1/train.normalized.jsonl")
    parser.add_argument("--validation", type=Path, default=ROOT / "data/review/sale-v1/validation.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    metadata, metrics = train_run(args.batch, args.train, args.validation, args.out, args.seed)
    print(json.dumps({"run": str(args.out), "train_records": metadata["train_records"],
                      "validation_records": metadata["validation_records"], "joint_micro_f1": metrics["joint"]["micro_f1"],
                      "sale_flag": metrics["sale_flag"]["per_label"]}, indent=2))


if __name__ == "__main__":
    main()
