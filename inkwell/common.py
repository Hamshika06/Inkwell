import hashlib
import json
import re
from pathlib import Path
import numpy as np
from sklearn.metrics import precision_recall_fscore_support, f1_score

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = json.loads((ROOT / "configs/label_schema.json").read_text())["categories"]

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def key(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def tune_thresholds(y, scores):
    # Validation only; conservative tie-breaking toward a larger threshold.
    return np.array([max(np.linspace(-3, 3, 121), key=lambda t: (f1_score(y[:, c], scores[:, c] >= t, zero_division=0), t))
                     for c in range(len(CATEGORIES))])

def full_metrics(rows, scores, thresholds):
    if not rows or any(r["label_mask"] != [1] * len(CATEGORIES) for r in rows):
        raise ValueError("Full precision/recall/F1 requires explicit positive AND negative judgments for every category")
    y = np.array([r["label_vec"] for r in rows]); pred = scores >= thresholds
    p, r, f, support = precision_recall_fscore_support(y, pred, average=None, zero_division=0)
    return {"macro_f1": float(f.mean()), "micro_f1": float(f1_score(y, pred, average="micro", zero_division=0)),
            "per_category": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                                 "positive_support": int(support[i]), "negative_support": int(len(y)-support[i])}
                             for i, c in enumerate(CATEGORIES)}}

def positive_recall(rows, scores, thresholds):
    y = np.array([r["label_vec"] for r in rows]); pred = scores >= thresholds
    return {"contract": "positive-label recall only; false positives are unmeasured; never use for model selection",
            "per_category": {c: {"positive_support": int(y[:,i].sum()),
                                   "recall": float(pred[y[:,i]==1,i].mean()) if y[:,i].sum() else None}
                             for i,c in enumerate(CATEGORIES)}}


def verified_dataset():
    path = ROOT / "data/versions/v1/classifier.jsonl"
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for file, expected in [(path, manifest["classifier_sha256"]),
                           (ROOT / "configs/label_schema.json", manifest["schema_sha256"]),
                           (ROOT / "configs/label_mapping.json", manifest["mapping_sha256"])]:
        if digest(file) != expected:
            raise ValueError(f"Frozen benchmark checksum mismatch: {file}")
    return path
