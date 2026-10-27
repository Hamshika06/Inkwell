"""Deterministic, evidence-linked screening of classified privacy clauses.

Weights and bands are provisional product choices, not learned risk estimates.
Only explicit supported wording contributes; absence of a match is not safety.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    title: str
    points: int
    pattern: str


DATA = r"(?:your\s+)?(?:personal\s+)?(?:data|information)"
ACTOR = r"\bwe\s+(?:(?:may|will|do)\s+)?"
RULES = (
    Rule("data_sale", "Third Party Sharing/Collection", "Sale of personal data", 30,
         ACTOR + r"sell\s+" + DATA + r"\b"),
    Rule("advertising_sharing", "Third Party Sharing/Collection", "Sharing with advertisers", 20,
         ACTOR + r"share\s+" + DATA + r"\s+with\s+(?:our\s+)?(?:advertisers|advertising partners)\b"),
    Rule("indefinite_retention", "Data Retention", "Indefinite data retention", 20,
         ACTOR + r"(?:retain|keep|store)\s+" + DATA + r"\s+(?:indefinitely|forever|without\s+(?:a\s+)?time\s+limit)\b"),
    Rule("dnt_not_honored", "Do Not Track", "Do Not Track signals not honored", 15,
         r"\bwe\s+(?:do\s+not|don't|don’t)\s+(?:currently\s+)?(?:honou?r|respond\s+to|recognize)\s+"
         r"(?:browser\s+)?(?:do[ -]not[ -]track|dnt)(?:\s+(?:signals|requests))?\b"),
    Rule("changes_without_notice", "Policy Change", "Policy changes without notice", 15,
         ACTOR + r"(?:change|update|modify)\s+(?:this|our|the)\s+(?:privacy\s+)?policy\s+"
         r"(?:at\s+any\s+time\s+)?without\s+(?:prior\s+)?(?:notice|notifying\s+you)\b"),
)
COMPILED = tuple((rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES)
REVIEW_CATEGORIES = (
    "Data Security", "Data Retention", "User Choice/Control", "User Access, Edit and Deletion",
)
LIMITATION = (
    "Experimental wording-based screening, not a probability of harm or a compliance assessment. "
    "Weights and bands are unvalidated. A zero score means no supported risk wording matched, "
    "not that the policy is safe. Classifier errors, paraphrases, exceptions and conflicting "
    "clauses can change the result. Review the source evidence."
)


def score_policy(segments):
    """Score Stage 1 segments, counting each rule once regardless of repetition.

    Evidence offsets use Python character indices, like Stage 1. Each finding
    includes every matching span; model margins never enter the risk arithmetic.
    """
    findings = []
    covered = {label for segment in segments for label in segment["labels"]}
    for rule, pattern in COMPILED:
        evidence = []
        for segment in segments:
            if rule.category not in segment["labels"]:
                continue
            for match in pattern.finditer(segment["text"]):
                evidence.append({
                    "segment_id": segment["id"],
                    "start": segment["start"] + match.start(),
                    "end": segment["start"] + match.end(),
                    "text": match.group(),
                })
        if evidence:
            findings.append({"rule_id": rule.id, "category": rule.category,
                             "title": rule.title, "points": rule.points, "evidence": evidence})
    score = sum(finding["points"] for finding in findings)
    # Zero is deliberately not labelled "low risk".
    band = "no_matches" if score == 0 else "low" if score < 25 else "moderate" if score < 50 else "high"
    return {"version": "1.0.0", "score": score, "max_score": sum(rule.points for rule in RULES),
            "band": band, "findings": findings,
            "review_gaps": [category for category in REVIEW_CATEGORIES if category not in covered],
            "limitation": LIMITATION}
