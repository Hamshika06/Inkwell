"""Turn the risk model's paragraph predictions into one selling verdict for a whole policy.

The risk model (inkwell/risk_baseline.py) labels each paragraph with (practice, actor, polarity)
triples. This module looks only at what the company itself says about selling or renting data
and picks the riskiest stance in the policy:

    permitted    50 points   "Sells your data"
    conditional  25 points   "May sell under some conditions"
    unclear       0 points   "Not clearly stated: the policy is vague about this"
    (nothing)     0 points   "Not clearly stated: the policy doesn't say"
    denied        0 points   "Says they don't sell"

Rules:
- Renting counts as selling. Business transfers (mergers, acquisitions) do not count.
- Only first_party counts; a service provider's practices are not the company selling.
- The riskiest stance wins. Other stances are kept in "also_says" so the user sees the conflict.
- Points are counted once per policy, however many paragraphs repeat the stance.
- Paragraphs under 5 words are headings and are skipped.
- Model margins are never used as probabilities; only the 0/1 predictions are read.

The verdict is only as good as the model's predictions; see runs/risk-actor-masked-tfidf-seed42.
"""

SALE_PRACTICES = ("sale", "rental")  # renting counts as selling
ORDER = ("permitted", "conditional", "unclear", "denied")  # riskiest first
POINTS = {"permitted": 50, "conditional": 25, "unclear": 0, "denied": 0, "not_stated": 0}
LABELS = {
    "permitted": "Sells your data",
    "conditional": "May sell under some conditions",
    "unclear": "Not clearly stated: the policy is vague about this",
    "not_stated": "Not clearly stated: the policy doesn't say",
    "denied": "Says they don't sell",
}
MIN_WORDS = 5  # shorter paragraphs are headings


def model_triples(model, texts):
    """Predicted triples for each text, from an ActorMaskedPredictor (0/1 predictions only)."""
    return [[t for t, hit in zip(model.triples, row) if hit] for row in model.predict(texts)]


def sale_stances(triples):
    """First-party selling/renting stances in one paragraph, riskiest first."""
    found = {polarity for practice, actor, polarity in triples
             if practice in SALE_PRACTICES and actor == "first_party"}
    return [p for p in ORDER if p in found]


def sale_verdict(paragraphs):
    """paragraphs: [{"id": ..., "text": str, "triples": [(practice, actor, polarity), ...]}, ...]"""
    evidence = {p: [] for p in ORDER}
    for para in paragraphs:
        if len(para["text"].split()) < MIN_WORDS:
            continue
        for stance in sale_stances(para["triples"]):
            evidence[stance].append({"id": para["id"], "text": para["text"]})

    verdict = next((p for p in ORDER if evidence[p]), "not_stated")
    also_says = [{"verdict": p, "label": LABELS[p], "evidence": evidence[p]}
                 for p in ORDER if p != verdict and evidence[p]]
    return {
        "verdict": verdict,
        "points": POINTS[verdict],
        "label": LABELS[verdict],
        "evidence": evidence.get(verdict, []),
        "also_says": also_says,  # shown as "But the policy also says"
    }