import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

CLASSES = [
    "Data Collection & Use",
    "Data Sharing",
    "User Rights & Choices",
    "Data Security & Retention",
    "Policy Scope & Changes",
]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TextRows(Dataset):
    def __init__(self, rows, tokenizer, max_length):
        self.rows = rows
        self.enc = tokenizer(
            [r["text"] for r in rows],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return {
            "input_ids": self.enc["input_ids"][i],
            "attention_mask": self.enc["attention_mask"][i],
            "index": i,
        }


def make_collator(tokenizer):
    def collate(batch):
        padded = tokenizer.pad(
            [{"input_ids": x["input_ids"],
              "attention_mask": x["attention_mask"]} for x in batch],
            padding=True,
            return_tensors="pt",
        )
        padded["index"] = torch.tensor([x["index"] for x in batch])
        return padded
    return collate


def predict_probs(model, loader, device):
    model.eval()
    probs, indices = [], []

    with torch.no_grad():
        for batch in loader:
            indices.extend(batch.pop("index").tolist())
            inputs = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(**inputs).logits
            probs.append(torch.sigmoid(logits).float().cpu().numpy())

    order = np.argsort(indices)
    return np.concatenate(probs)[order]


def masked_metrics(rows, probs, thresholds):
    y = np.asarray([r["label_vec"] for r in rows], dtype=int)
    mask = np.asarray([r["label_mask"] for r in rows], dtype=bool)
    pred = probs >= np.asarray(thresholds)[None, :]

    per_class = {}
    class_f1s = []

    for c, name in enumerate(CLASSES):
        known = mask[:, c]
        if not known.any():
            per_class[name] = {
                "precision": None, "recall": None, "f1": None,
                "known": 0, "support": 0,
            }
            continue

        yt, yp = y[known, c], pred[known, c]
        p, r, f, _ = precision_recall_fscore_support(
            yt, yp, average="binary", zero_division=0
        )
        per_class[name] = {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "known": int(known.sum()),
            "support": int(yt.sum()),
        }
        class_f1s.append(float(f))

    known_cells = mask.ravel()
    micro = f1_score(
        y.ravel()[known_cells],
        pred.ravel()[known_cells],
        average="binary",
        zero_division=0,
    )
    return {
        "macro_f1": float(np.mean(class_f1s)) if class_f1s else 0.0,
        "micro_f1": float(micro),
        "per_class": per_class,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed_five_class")
    parser.add_argument("--model-dir", default="artifacts/roberta-five-class")
    parser.add_argument("--out-dir", default="runs/roberta-five-class")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 7, 13])
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--top-errors", type=int, default=20)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not detected. Enable a GPU runtime.")
    device = torch.device("cuda")

    rows = read_jsonl(Path(args.data_dir) / "test.jsonl")
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_metrics = []

    for seed in args.seeds:
        seed_dir = Path(args.model_dir) / f"seed_{seed}"
        tokenizer = AutoTokenizer.from_pretrained(seed_dir / "tokenizer")
        model = AutoModelForSequenceClassification.from_pretrained(
            seed_dir / "model"
        ).to(device)

        with open(seed_dir / "thresholds.json", encoding="utf-8") as f:
            thresholds_by_class = json.load(f)
        thresholds = [thresholds_by_class[name] for name in CLASSES]

        dataset = TextRows(rows, tokenizer, args.max_length)
        loader = DataLoader(
            dataset, batch_size=16, shuffle=False,
            collate_fn=make_collator(tokenizer),
        )
        probs = predict_probs(model, loader, device)

        overall = masked_metrics(rows, probs, thresholds)
        by_source = {}
        for source in ["opp115", "policyie", "goppc"]:
            indices = [i for i, row in enumerate(rows)
                       if row["source"] == source]
            if indices:
                by_source[source] = masked_metrics(
                    [rows[i] for i in indices], probs[indices], thresholds
                )

        result = {
            "seed": seed,
            "test_overall": overall,
            "test_by_source": by_source,
            "thresholds": thresholds_by_class,
        }
        with open(output_dir / f"results_seed{seed}.json", "w") as f:
            json.dump(result, f, indent=2)

        seed_metrics.append(result)
        print(f"Seed {seed}: {json.dumps(overall)}")

        # Save highest-confidence wrong known predictions for review.
        y = np.asarray([r["label_vec"] for r in rows], dtype=int)
        mask = np.asarray([r["label_mask"] for r in rows], dtype=bool)
        pred = probs >= np.asarray(thresholds)[None, :]
        errors = []

        for i, row in enumerate(rows):
            for c, name in enumerate(CLASSES):
                if not mask[i, c]:
                    continue
                if pred[i, c] and not y[i, c]:
                    errors.append({
                        "confidence": float(probs[i, c]),
                        "error": "false_positive",
                        "class": name,
                        "source": row["source"],
                        "id": row.get("id"),
                        "text": row["text"][:500],
                    })
                elif not pred[i, c] and y[i, c]:
                    errors.append({
                        "confidence": float(1.0 - probs[i, c]),
                        "error": "false_negative",
                        "class": name,
                        "source": row["source"],
                        "id": row.get("id"),
                        "text": row["text"][:500],
                    })

        errors.sort(key=lambda x: x["confidence"], reverse=True)
        with open(output_dir / f"errors_seed{seed}.json", "w") as f:
            json.dump(errors[:args.top_errors], f, indent=2)

    summary = {}
    for metric in ["macro_f1", "micro_f1"]:
        values = [r["test_overall"][metric] for r in seed_metrics]
        summary[metric] = {
            "mean": float(np.mean(values)),
            "std_population": float(np.std(values)),
            "per_seed": values,
        }

    summary["per_class_f1"] = {}
    for name in CLASSES:
        values = [
            r["test_overall"]["per_class"][name]["f1"]
            for r in seed_metrics
        ]
        summary["per_class_f1"][name] = {
            "mean": float(np.nanmean(values)),
            "std_population": float(np.nanstd(values)),
            "per_seed": values,
        }

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("Wrote per-seed results, error examples, and summary to", output_dir)


if __name__ == "__main__":
    main()