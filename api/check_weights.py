"""Check recovered encoder weights against their run: python -m api.check_weights runs/roberta-opp115-seed42

Thresholds in a run folder were tuned for that exact checkpoint. This rescoring of the OPP-115
validation split (never test) must reproduce validation_metrics.json, or the weights belong to another run.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from inkwell.common import full_metrics, verified_dataset
from inkwell.predict import Predictor


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--tolerance", type=float, default=0.005)
    args = ap.parse_args()
    run = Path(args.run)
    rows = [json.loads(line) for line in verified_dataset().read_text(encoding="utf-8").splitlines() if line.strip()]
    val = [r for r in rows if r["split"] == "validation" and r["source"] == "opp115"]
    predictor = Predictor(run)
    print(f"Scoring {len(val)} validation rows with {run.name} on CPU...", flush=True)
    measured = full_metrics(val, np.asarray(predictor.scores([r["text"] for r in val])), predictor.thresholds)["macro_f1"]
    recorded = json.loads((run / "validation_metrics.json").read_text())["macro_f1"]
    ok = abs(measured - recorded) <= args.tolerance
    print(f"validation macro-F1: measured {measured:.4f}, recorded {recorded:.4f} -> {'MATCH' if ok else 'MISMATCH'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
