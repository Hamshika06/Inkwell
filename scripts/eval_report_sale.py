"""Measure the report card's "Sells your data" check against Gowtham's reviewed sale-v1 labels.

    python -m scripts.eval_report_sale [--show-errors]

Each reviewed row is one policy paragraph with one or more sale propositions labelled permitted, conditional,
denied or unclear, or marked not sale-related. The row's expected verdict:
  found   - any permitted or conditional proposition (the card says "Yes, or it may count as a sale")
  denied  - only denied propositions
  missing - not sale-related (product sales, business transfers, ...)
Rows whose only label is unclear are reported but not scored. Only train.reviewed.jsonl carries review
labels so far; validation and test rows are still unreviewed.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from inkwell.report import build_report
from inkwell.stage1 import segment

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/review/sale-v1"


def expected(review):
    if not review.get("sale_related"):
        return "missing"
    labels = {p["label"] for p in review.get("practices", [])}
    if labels & {"permitted", "conditional"}:
        return "found"
    if "denied" in labels:
        return "denied"
    return "unclear"


# The card's finer verdicts, folded onto the review labels: "Only if you agree", "Says they don't, with
# exceptions" and "Only if the company is sold" are conditional permissions in the review schema.
FOLD = {"found": "found", "consent": "found", "transfer": "found", "exceptions": "found", "denied": "denied", "missing": "missing"}


def predicted(text):
    checks = {c["id"]: c for c in build_report(segment(text))["checks"]}
    return checks["sale"]["state"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()
    rows = []
    for name in ("train.reviewed.jsonl", "validation.jsonl", "test.jsonl"):
        for line in (DATA / name).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (row.get("review") or {}).get("sale_related") is not None:  # Skip unreviewed skeletons.
                rows.append(row)
    pairs = [(expected(r["review"]), predicted(r["text"]), r) for r in rows]
    print("card verdicts:", dict(Counter(p for _, p, _ in pairs)))
    pairs = [(g, FOLD[p], r) for g, p, r in pairs]
    scored = [(g, p, r) for g, p, r in pairs if g != "unclear"]
    states = ("found", "denied", "missing")
    confusion = Counter((g, p) for g, p, _ in scored)

    print(f"sale-v1 reviewed rows: {len(rows)}  scored: {len(scored)}  unclear (not scored): {len(rows) - len(scored)}\n")
    print("expected \\ predicted " + "".join(f"{s:>10}" for s in states))
    for g in states:
        print(f"{g:<20}" + "".join(f"{confusion[(g, p)]:>10}" for p in states))
    print()
    for s in states:
        tp = confusion[(s, s)]
        pred = sum(confusion[(g, s)] for g in states)
        gold = sum(confusion[(s, p)] for p in states)
        precision = tp / pred if pred else float("nan")
        recall = tp / gold if gold else float("nan")
        print(f"{s:<8} precision {precision:.2f} ({tp}/{pred})   recall {recall:.2f} ({tp}/{gold})")
    accuracy = sum(confusion[(s, s)] for s in states) / len(scored)
    # The error that matters most: telling someone a company doesn't sell when the policy says it may.
    wrong_reassurance = confusion[("found", "denied")]
    print(f"\naccuracy {accuracy:.2f}   'Says they don't' when the policy allows sale: {wrong_reassurance}")

    if args.show_errors:
        for g, p, r in scored:
            if g != p:
                print(f"\n--- expected {g}, predicted {p}  [{r['id']}]\n{r['text'][:600]}")


if __name__ == "__main__":
    main()
