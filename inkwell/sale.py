"""Experimental paragraph-level TF-IDF practice/polarity baseline."""
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC


def label_pairs(schema):
    return [(practice, polarity) for practice in schema["practice_types"] for polarity in schema["labels"]]


def targets(rows, pairs):
    """Keep every scoped proposition as a paragraph-level label, including opposites."""
    result = np.zeros((len(rows), len(pairs)), dtype=int)
    index = {pair: i for i, pair in enumerate(pairs)}
    for i, row in enumerate(rows):
        for practice in row["review"]["practices"]:
            result[i, index[(practice["practice_type"], practice["label"])]] = 1
    return result


class SalePredictor:
    """Predict sets of practice/polarity pairs from full paragraph text.

    Annotation spans are never inference inputs. Predictions have no extracted
    scope or supporting spans; they reference the input paragraph only.
    """
    def __init__(self, pairs, seed=42):
        self.pairs = list(pairs)
        self.seed = seed
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1,
                                          max_features=20000, sublinear_tf=True)

    def fit(self, texts, y):
        x = self.vectorizer.fit_transform(texts)
        self.models = []
        for column in y.T:
            if len(np.unique(column)) == 1:
                self.models.append(int(column[0]))
            else:
                model = LinearSVC(C=1.0, class_weight="balanced", random_state=self.seed)
                self.models.append(model.fit(x, column))
        return self

    def scores(self, texts):
        if not texts:
            return np.empty((0, len(self.pairs)))
        x = self.vectorizer.transform(texts)
        return np.column_stack([np.full(len(texts), 1.0 if model else -1.0)
                                if isinstance(model, int) else model.decision_function(x)
                                for model in self.models])

    def predict(self, texts):
        return (self.scores(texts) >= 0).astype(int)

    def save(self, path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        return joblib.load(path)


def multilabel_metrics(y, predicted, names):
    """Confusion counts per label, with null recall when validation support is zero."""
    per_label = {}
    for i, name in enumerate(names):
        truth, guess = y[:, i].astype(bool), predicted[:, i].astype(bool)
        tp, fp = int((truth & guess).sum()), int((~truth & guess).sum())
        fn, tn = int((truth & ~guess).sum()), int((~truth & ~guess).sum())
        per_label[name] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "support": tp + fn,
                           "precision": tp / (tp + fp) if tp + fp else None,
                           "recall": tp / (tp + fn) if tp + fn else None,
                           "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                           "confusion_matrix": [[tn, fp], [fn, tp]]}
    tp = sum(r["tp"] for r in per_label.values())
    fp = sum(r["fp"] for r in per_label.values())
    fn = sum(r["fn"] for r in per_label.values())
    supported = [r["f1"] for r in per_label.values() if r["support"] > 0]
    return {"records": len(y), "micro_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "macro_f1_supported": float(np.mean(supported)) if supported else None,
            "exact_match": float((y == predicted).all(axis=1).mean()) if len(y) else None,
            "per_label": per_label}
