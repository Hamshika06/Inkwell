#!/usr/bin/env python3
"""
Clean the preprocessed C3PA units (data/interim/c3pa.jsonl) into a v2 candidate.

Usage:
    python data_integration/clean_c3pa_v2.py
    python data_integration/clean_c3pa_v2.py --min-words 10 --max-words 400 --out data/interim/c3pa_v2

What it does, in this order
    1. repairs encoding damage (UTF-8 read as cp1252, e.g. "â€™" -> "’", stray C1 control characters)
    2. drops fragments: units under --min-words words (headings, table cells, "Last updated: ...")
    3. drops units over --max-words words (table/chart dumps; the encoder would only see a window of them)
    4. drops units that are mostly non-letters (addresses, phone numbers, widget text)
    5. removes duplicates created by step 1; copies with conflicting labels are all dropped
    6. adds quality_weight from the number of annotators (1 -> 0.5, 2 -> 0.75, 3+ -> 1.0)
    7. writes label_review.csv: units whose label looks suspicious, for a hand audit (labels are NOT changed)

Labels, label masks, doc_id and group_id are never edited, so company-level splits stay valid.

Outputs (in --out, default data/interim/c3pa_v2)
    c3pa.jsonl           cleaned units, same fields as data/interim/c3pa.jsonl plus quality_weight
    dropped_units.csv    every removed unit with the reason
    label_review.csv     suspicious-label candidates for manual review
    clean_report.txt     counts before/after, per category and per reason

Then feed it to the existing integration script:
    python data_integration/combine_opp115_c3pa.py --opp-dir data/interim --c3pa data/interim/c3pa_v2/c3pa.jsonl \
        --opp-docs preprocessing/reports/opp115/opp115_docs.csv --out data/processed_v2 --c3pa-mask positive
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = json.loads((ROOT / "configs" / "label_schema.json").read_text())["categories"]

# ---------------------------------------------------------------- 1. encoding repair
try:  # ftfy is optional; the fallback below covers the damage seen in C3PA
    from ftfy import fix_text as _ftfy
except ImportError:
    _ftfy = None

MOJIBAKE = re.compile(r"[ÂÃâ][\x80-\xbfŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™]")
C1 = re.compile(r"[\x80-\x9f]")


def _c1_to_cp1252(m):
    try:
        return bytes([ord(m.group())]).decode("cp1252")
    except UnicodeDecodeError:
        return " "


def _to_bytes(chars):
    # cp1252 has no mapping for 0x81/0x8d/0x8f/0x90/0x9d; those survive as C1 characters, so fall back to latin-1.
    out = bytearray()
    for ch in chars:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            out += ch.encode("latin-1")
    return bytes(out)


def _undo_mojibake(s):
    # Re-encode as cp1252 and decode as UTF-8; keep the original if that does not round-trip.
    def fix(m):
        try:
            return _to_bytes(m.group()).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return m.group()
    s = re.sub(r"[ÂÃâ][-¿ŒœŠšŸŽžƒˆ˜"
               r"–—‘-„†-•…‰‹›€™]{1,2}", fix, s)
    return s.replace("â€", "")  # truncated quote/dash sequence whose last byte was lost


def repair(text):
    if _ftfy:
        text = _ftfy(text)
    else:
        text = _undo_mojibake(text)
    text = C1.sub(_c1_to_cp1252, text)
    text = text.replace("�", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def had_damage(text):
    return bool(MOJIBAKE.search(text) or C1.search(text) or "�" in text)


# ---------------------------------------------------------------- helpers
def text_key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def alpha_ratio(s):
    return sum(c.isalpha() for c in s) / max(len(s), 1)


def quality_weight(n_annotators):
    return 0.5 if n_annotators <= 1 else 0.75 if n_annotators == 2 else 1.0


# Rough keyword sanity checks; a unit with none of them is only *flagged* for review.
EXPECTED = {
    "Policy Change": r"chang|updat|revis|modif|amend|effective|last|notif",
    "User Choice/Control": r"opt|choice|choose|limit|unsubscribe|prefer|consent|do not sell|restrict|object",
    "User Access, Edit and Deletion": r"delet|access|correct|know|request|erase|rectif|copy|portab|remov|inform",
    "Third Party Sharing/Collection": r"third|share|disclos|sell|sold|partner|affiliat|provider|vendor|advertis|analytic|categor|transfer|recipient|collect",
    "First Party Collection/Use": r"collect|categor|information|data|receive|obtain|gather|use|identif|record",
}
EXPECTED = {k: re.compile(v, re.I) for k, v in EXPECTED.items()}
# A Policy Change label is also suspicious when the text is plainly about something else.
INTRO_RE = re.compile(r"^(.{0,80})\b(on behalf of|this (privacy )?(statement|notice|policy) (discloses|describes|applies))", re.I)


def review_reasons(unit):
    reasons = []
    for lab in unit["labels"]:
        rx = EXPECTED.get(lab)
        if rx and not rx.search(unit["text"]):
            reasons.append(f"no expected keyword for {lab}")
    if "Policy Change" in unit["labels"] and INTRO_RE.search(unit["text"]) and "change" not in unit["text"].lower():
        reasons.append("Policy Change label on an introductory sentence")
    if "User Choice/Control" in unit["labels"] and re.search(r"changes? to (this|our|the) (privacy )?(policy|notice|statement)", unit["text"][:80], re.I):
        reasons.append("User Choice label on a policy-change heading")
    return reasons


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(ROOT / "data/interim/c3pa.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "data/interim/c3pa_v2"))
    ap.add_argument("--min-words", type=int, default=10)
    ap.add_argument("--max-words", type=int, default=400, help="0 keeps long units")
    ap.add_argument("--min-alpha", type=float, default=0.6, help="drop units with a smaller share of letters")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; pick a new --out (versions are never overwritten)")
    units = [json.loads(l) for l in open(args.src, encoding="utf-8") if l.strip()]
    for u in units:
        assert set(u["labels"]) <= set(CATEGORIES), f"unknown label in {u['unit_id']}"

    dropped, kept, repaired = [], [], 0
    for u in units:
        damaged = had_damage(u["text"])
        text = repair(u["text"])
        repaired += damaged and text != u["text"]
        words = len(text.split())
        reason = None
        if words < args.min_words:
            reason = f"fewer than {args.min_words} words"
        elif args.max_words and words > args.max_words:
            reason = f"more than {args.max_words} words"
        elif alpha_ratio(text) < args.min_alpha:
            reason = "mostly non-letters"
        if reason:
            dropped.append((u, reason))
            continue
        kept.append({**u, "text": text, "n_words": words, "quality_weight": quality_weight(u.get("n_annotators", 1))})

    # Duplicates (including new ones created by the repair); conflicting labels drop every copy.
    by_key = {}
    for u in kept:
        by_key.setdefault(text_key(u["text"]), []).append(u)
    final = []
    for k, group in by_key.items():
        label_sets = {tuple(sorted(g["labels"])) for g in group}
        if len(label_sets) > 1:
            dropped += [(g, "same text, conflicting labels after cleaning") for g in group]
        else:
            final.append(group[0])
            dropped += [(g, "duplicate text after cleaning (first copy kept)") for g in group[1:]]
    order = {u["unit_id"]: i for i, u in enumerate(units)}
    final.sort(key=lambda u: order[u["unit_id"]])

    review = []
    for u in final:
        why = review_reasons(u)
        if why:
            review.append((u, "; ".join(why)))

    out.mkdir(parents=True)
    (out / "c3pa.jsonl").write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in final), encoding="utf-8")
    with open(out / "dropped_units.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_id", "reason", "labels", "text"])
        for u, why in dropped:
            w.writerow([u["unit_id"], why, "|".join(u["labels"]), u["text"][:300]])
    with open(out / "label_review.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_id", "labels", "n_annotators", "reason", "text", "correct_labels (fill in)"])
        for u, why in review:
            w.writerow([u["unit_id"], "|".join(u["labels"]), u["n_annotators"], why, u["text"][:400], ""])

    def per_cat(rows):
        c = Counter(l for r in rows for l in r["labels"])
        return {k: c.get(k, 0) for k in CATEGORIES if c.get(k, 0)}
    lines = [f"source: {args.src}",
             f"settings: min_words={args.min_words} max_words={args.max_words} min_alpha={args.min_alpha} ftfy={'yes' if _ftfy else 'no (built-in fallback)'}",
             f"units before: {len(units)}   after: {len(final)}   dropped: {len(units) - len(final)}",
             f"units with encoding damage repaired: {repaired}",
             "", "dropped by reason:"]
    lines += [f"  {n:6d}  {r}" for r, n in Counter(r for _, r in dropped).most_common()]
    lines += ["", "label counts before -> after:"]
    b, a = per_cat(units), per_cat(final)
    lines += [f"  {k:40s} {b.get(k, 0):6d} -> {a.get(k, 0):6d}" for k in b]
    lines += ["", f"units with n_annotators=1: {sum(u['n_annotators'] <= 1 for u in final)} of {len(final)} (quality_weight 0.5)",
              f"units flagged for label review: {len(review)} (see label_review.csv; labels were not changed)",
              f"companies (group_id) before: {len({u['group_id'] for u in units})}  after: {len({u['group_id'] for u in final})}"]
    (out / "clean_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
