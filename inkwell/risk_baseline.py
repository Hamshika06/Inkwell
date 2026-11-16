"""Actor-aware paragraph classification with explicit unknown-target masking."""
import itertools

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC


def target_triples(schema):
    return list(itertools.product(schema["practice_types"], schema["actors"], schema["labels"]))


def coverage_targets(rows, triples):
    """Conservatively expand practice coverage without inventing actor negatives."""
    y = np.zeros((len(rows), len(triples)), dtype=int)
    mask = np.zeros_like(y)
    for i, row in enumerate(rows):
        review = row["risk_review"]
        if review["status"] != "annotated":
            continue
        practices = review["practices"]
        positive = {(p["practice_type"], p["actor"], p["label"]) for p in practices}
        covered = set(review["covered_practice_types"])
        for j, (practice, actor, polarity) in enumerate(triples):
            if practice not in covered:
                continue
            actors = {p["actor"] for p in practices if p["practice_type"] == practice}
            if not actors or actor in actors:
                mask[i, j] = 1
                y[i, j] = int((practice, actor, polarity) in positive)
    return y, mask


def validate_target_arrays(y, mask):
    if y.shape != mask.shape or y.ndim != 2:
        raise ValueError("Targets and masks must have the same two-dimensional shape")
    if not np.isin(y, [0, 1]).all() or not np.isin(mask, [0, 1]).all():
        raise ValueError("Targets and masks must be binary")
    if (y > mask).any():
        raise ValueError("Positive target cannot be masked unknown")


class ActorMaskedPredictor:
    def __init__(self, triples, seed=42):
        self.triples = list(triples)
        self.seed = seed
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1,
                                          max_features=20000, sublinear_tf=True)

    def fit(self, texts, y, mask):
        validate_target_arrays(y, mask)
        if len(texts) != len(y) or y.shape[1] != len(self.triples):
            raise ValueError("Text/target/label dimensions differ")
        included = mask.any(axis=1)
        if not included.any():
            raise ValueError("No known risk targets to train on")
        # Even vocabulary fitting excludes every completely unknown paragraph.
        selected_texts = [t for t, keep in zip(texts, included) if keep]
        x = self.vectorizer.fit_transform(selected_texts)
        y, mask = y[included], mask[included]
        self.models, self.training_support = [], []
        for i in range(y.shape[1]):
            known = mask[:, i].astype(bool)
            column = y[known, i]
            support = {"known": int(known.sum()), "positive": int(column.sum()),
                       "negative": int(len(column) - column.sum())}
            if not len(column):
                model, state = None, "unknown"
            elif len(np.unique(column)) == 1:
                model = int(column[0])
                state = "positive_only" if model else "negative_only"
            else:
                model = LinearSVC(C=1.0, class_weight="balanced", random_state=self.seed)
                model.fit(x[known], column)
                state = "learned"
            self.models.append(model)
            self.training_support.append(dict(support, state=state))
        self.fitted_records = len(selected_texts)
        return self

    def scores(self, texts):
        if not texts:
            return np.empty((0, len(self.triples)))
        x = self.vectorizer.transform(texts)
        columns = []
        for model in self.models:
            if model is None:
                columns.append(np.full(len(texts), np.nan))
            elif isinstance(model, int):
                columns.append(np.full(len(texts), 1.0 if model else -1.0))
            else:
                columns.append(model.decision_function(x))
        return np.column_stack(columns)

    def predict(self, texts):
        scores = self.scores(texts)
        return (np.isfinite(scores) & (scores >= 0)).astype(int)

    def save(self, path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        return joblib.load(path)


def masked_metrics(y, predicted, mask, names):
    validate_target_arrays(y, mask)
    if predicted.shape != y.shape or len(names) != y.shape[1]:
        raise ValueError("Prediction/target/label dimensions differ")
    if not np.isin(predicted, [0, 1]).all():
        raise ValueError("Predictions must be binary")
    per_target = {}
    for j, name in enumerate(names):
        known = mask[:, j].astype(bool)
        truth, guess = y[:, j].astype(bool), predicted[:, j].astype(bool)
        tp = int((known & truth & guess).sum())
        fp = int((known & ~truth & guess).sum())
        fn = int((known & truth & ~guess).sum())
        tn = int((known & ~truth & ~guess).sum())
        per_target[name] = {"known": int(known.sum()), "unknown": int((~known).sum()),
                            "positive_support": tp + fn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                            "precision": tp / (tp + fp) if tp + fp else None,
                            "recall": tp / (tp + fn) if tp + fn else None,
                            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                            "confusion_matrix": [[tn, fp], [fn, tp]]}
    tp, fp, fn = (sum(r[k] for r in per_target.values()) for k in ("tp", "fp", "fn"))
    supported = [r["f1"] for r in per_target.values() if r["positive_support"] > 0]
    any_known, fully_known = mask.any(axis=1), mask.all(axis=1)
    matches = ((y == predicted) | (mask == 0)).all(axis=1)
    return {"records": len(y), "records_with_known_targets": int(any_known.sum()),
            "known_cells": int(mask.sum()), "unknown_cells": int(mask.size - mask.sum()),
            "micro_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "macro_f1_supported": float(np.mean(supported)) if supported else None,
            "masked_exact_match": float(matches[any_known].mean()) if any_known.any() else None,
            "fully_known_records": int(fully_known.sum()),
            "fully_known_exact_match": float(matches[fully_known].mean()) if fully_known.any() else None,
            "per_target": per_target}


def aggregate_or(y, predicted, mask, columns):
    """Three-valued OR: positive is known; negative needs all inputs known."""
    truth = y[:, columns].any(axis=1).astype(int)[:, None]
    known = (truth[:, 0].astype(bool) | mask[:, columns].all(axis=1))[:, None].astype(int)
    guesses = predicted[:, columns].any(axis=1).astype(int)[:, None]
    return truth, guesses, known


def evaluate_masked(y, predicted, mask, triples):
    names = ["/".join(t) for t in triples]
    result = {"joint": masked_metrics(y, predicted, mask, names), "by_practice": {}, "by_actor": {}}
    for dimension, field in [(0, "by_practice"), (1, "by_actor")]:
        for value in dict.fromkeys(t[dimension] for t in triples):
            columns = [j for j, t in enumerate(triples) if t[dimension] == value]
            result[field][value] = masked_metrics(y[:, columns], predicted[:, columns], mask[:, columns], [names[j] for j in columns])
    columns = [j for j, t in enumerate(triples) if t[0] == "sale" and t[1] == "first_party" and t[2] in ("permitted", "conditional")]
    if columns:
        truth, guesses, known = aggregate_or(y, predicted, mask, columns)
        result["first_party_sale_flag"] = masked_metrics(truth, guesses, known, ["first_party_sale_permitted_or_conditional"])
    return result
