import argparse
import json
import math
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Dataset, Sampler
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

CLASSES = [
    "Data Collection & Use",
    "Data Sharing",
    "User Rights & Choices",
    "Data Security & Retention",
    "Policy Scope & Changes",
]
SEEDS = [42, 7, 13]
POS_WEIGHT = [1.40, 3.65, 3.44, 8.17, 9.24]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class TextRows(Dataset):
    def __init__(self, rows, tokenizer, max_length):
        self.rows = rows
        self.enc = tokenizer(
            [r["text"] for r in rows],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        self.lengths = [len(ids) for ids in self.enc["input_ids"]]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return {
            "input_ids": self.enc["input_ids"][i],
            "attention_mask": self.enc["attention_mask"][i],
            "labels": self.rows[i]["label_vec"],
            "mask": self.rows[i]["label_mask"],
            "index": i,
        }


def make_collator(tokenizer):
    def collate(batch):
        inputs = tokenizer.pad(
            [{"input_ids": x["input_ids"],
              "attention_mask": x["attention_mask"]} for x in batch],
            padding=True,
            return_tensors="pt",
        )
        inputs["labels"] = torch.tensor(
            [x["labels"] for x in batch], dtype=torch.float
        )
        inputs["mask"] = torch.tensor(
            [x["mask"] for x in batch], dtype=torch.float
        )
        inputs["index"] = torch.tensor([x["index"] for x in batch])
        return inputs
    return collate


class LengthGroupedBatchSampler(Sampler):
    def __init__(self, lengths, batch_size, seed, bucket_size=512):
        self.lengths = lengths
        self.batch_size = batch_size
        self.seed = seed
        self.bucket_size = bucket_size
        self.epoch = 0

    def set_epoch(self, epoch):
        self.epoch = epoch

    def __iter__(self):
        rng = random.Random(self.seed + self.epoch)
        indices = list(range(len(self.lengths)))
        rng.shuffle(indices)

        batches = []
        for start in range(0, len(indices), self.bucket_size):
            bucket = indices[start:start + self.bucket_size]
            bucket.sort(key=lambda i: self.lengths[i])
            batches.extend(
                bucket[i:i + self.batch_size]
                for i in range(0, len(bucket), self.batch_size)
            )
        rng.shuffle(batches)
        yield from batches

    def __len__(self):
        return math.ceil(len(self.lengths) / self.batch_size)


def predict_probs(model, loader, device):
    model.eval()
    probs, indices = [], []

    with torch.no_grad():
        for batch in loader:
            indices.extend(batch.pop("index").tolist())
            batch.pop("labels")
            batch.pop("mask")
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


def tune_thresholds(rows, probs):
    y = np.asarray([r["label_vec"] for r in rows], dtype=int)
    mask = np.asarray([r["label_mask"] for r in rows], dtype=bool)
    thresholds = []

    for c in range(len(CLASSES)):
        known = mask[:, c]
        best_score, best_threshold = -1.0, 0.5
        for threshold in np.arange(0.05, 0.951, 0.01):
            score = (
                f1_score(y[known, c], probs[known, c] >= threshold,
                         zero_division=0)
                if known.any() else 0.0
            )
            if score > best_score or (
                score == best_score and threshold > best_threshold
            ):
                best_score, best_threshold = score, float(threshold)
        thresholds.append(best_threshold)

    return thresholds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed_five_class")
    parser.add_argument("--out-dir", default="artifacts/roberta-five-class")
    parser.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=512)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not detected. Enable a GPU runtime.")
    device = torch.device("cuda")

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Training and validation only. Test is loaded by the evaluation script.
    train_rows = read_jsonl(data_dir / "train.jsonl")
    val_rows = read_jsonl(data_dir / "validation.jsonl")

    tokenizer = AutoTokenizer.from_pretrained("roberta-base")
    train_ds = TextRows(train_rows, tokenizer, args.max_length)
    val_ds = TextRows(val_rows, tokenizer, args.max_length)
    collate = make_collator(tokenizer)

    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate
    )

    for seed in args.seeds:
        print(f"\n===== Seed {seed} =====")
        seed_everything(seed)

        model = AutoModelForSequenceClassification.from_pretrained(
            "roberta-base",
            num_labels=len(CLASSES),
            problem_type="multi_label_classification",
            id2label=dict(enumerate(CLASSES)),
            label2id={name: i for i, name in enumerate(CLASSES)},
        ).to(device)

        sampler = LengthGroupedBatchSampler(
            train_ds.lengths, args.batch_size, seed
        )
        train_loader = DataLoader(
            train_ds, batch_sampler=sampler, collate_fn=collate
        )

        optimizer = torch.optim.AdamW(
            model.parameters(), lr=2e-5, weight_decay=0.01
        )
        updates_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
        total_steps = updates_per_epoch * args.epochs
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            int(total_steps * 0.06),
            total_steps,
        )
        scaler = torch.amp.GradScaler("cuda")
        pos_weight = torch.tensor(POS_WEIGHT, dtype=torch.float, device=device)

        best_f1 = -1.0
        best_epoch = 0
        stale_epochs = 0
        best_state = None
        history = []

        for epoch in range(args.epochs):
            sampler.set_epoch(epoch)
            model.train()
            optimizer.zero_grad(set_to_none=True)
            epoch_loss = 0.0

            for step, batch in enumerate(train_loader):
                batch.pop("index")
                labels = batch.pop("labels").to(device)
                mask = batch.pop("mask").to(device)
                inputs = {k: v.to(device) for k, v in batch.items()}

                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
                    cell_loss = F.binary_cross_entropy_with_logits(
                        logits, labels, pos_weight=pos_weight,
                        reduction="none",
                    )
                    loss = (cell_loss * mask).sum() / mask.sum().clamp_min(1)
                    loss = loss / args.grad_accum

                scaler.scale(loss).backward()
                epoch_loss += loss.item() * args.grad_accum

                if ((step + 1) % args.grad_accum == 0
                        or step + 1 == len(train_loader)):
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
                    scheduler.step()

            val_probs = predict_probs(model, val_loader, device)
            val_metrics = masked_metrics(
                val_rows, val_probs, [0.5] * len(CLASSES)
            )
            record = {
                "epoch": epoch + 1,
                "train_loss_per_batch": epoch_loss / len(train_loader),
                "validation_macro_f1_at_0.5": val_metrics["macro_f1"],
            }
            history.append(record)
            print(record)

            if val_metrics["macro_f1"] > best_f1:
                best_f1 = val_metrics["macro_f1"]
                best_epoch = epoch + 1
                best_state = {
                    k: v.detach().cpu().clone()
                    for k, v in model.state_dict().items()
                }
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= args.patience:
                    print("Early stopping.")
                    break

        # Restore best validation checkpoint and tune thresholds on validation.
        model.load_state_dict(best_state)
        model.to(device)
        val_probs = predict_probs(model, val_loader, device)
        thresholds = tune_thresholds(val_rows, val_probs)
        val_metrics = masked_metrics(val_rows, val_probs, thresholds)

        seed_dir = out_dir / f"seed_{seed}"
        seed_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(seed_dir / "model")
        tokenizer.save_pretrained(seed_dir / "tokenizer")

        with open(seed_dir / "thresholds.json", "w") as f:
            json.dump(dict(zip(CLASSES, thresholds)), f, indent=2)
        with open(seed_dir / "training.json", "w") as f:
            json.dump({
                "seed": seed,
                "best_epoch": best_epoch,
                "history": history,
                "validation_metrics_at_tuned_thresholds": val_metrics,
                "thresholds": dict(zip(CLASSES, thresholds)),
                "config": {
                    "model": "roberta-base",
                    "max_length": args.max_length,
                    "learning_rate": 2e-5,
                    "batch_size": args.batch_size,
                    "gradient_accumulation": args.grad_accum,
                    "effective_batch_size": args.batch_size * args.grad_accum,
                    "epochs_max": args.epochs,
                    "early_stopping_patience": args.patience,
                    "warmup_ratio": 0.06,
                    "weight_decay": 0.01,
                    "gradient_clip_norm": 1.0,
                    "pos_weight": POS_WEIGHT,
                    "fp16": True,
                    "classes": CLASSES,
                },
            }, f, indent=2)

        print(f"Saved seed {seed} to {seed_dir}")


if __name__ == "__main__":
    main()