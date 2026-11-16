# Legacy sale-regex diagnostic

Checked 26 source records by ID and exact paragraph text. Recomputed matches: 0 ungated, 0 category-gated. Stored-flag mismatches: 0.

## Exact pattern

```regex
\bwe\s+(?:(?:may|will|do)\s+)?sell\s+(?:your\s+)?(?:personal\s+)?(?:data|information)\b
```

These are legacy affirmative-sale risk flags, not sale-mention or polarity predictions. Denials should not trigger them. Quoted rental, coordinated verbs, passive voice and named company subjects are outside this narrow pattern. Agreement verifies its application, not its adequacy as a competitive regex baseline.

## Synthetic controls

| Text | Expected risk flag | Actual |
| --- | --- | --- |
| We sell your personal information. | True | True |
| We may sell your personal data. | True | True |
| We will sell personal information. | True | True |
| We do not sell your personal information. | False | False |
| We will not sell your personal information. | False | False |
| We "rent" our marketing list. | False | False |

A false flag does not mean no sale-related language exists. Denials are intentionally excluded; rental/list wording and richer affirmative/conditional phrasing can be missed. The original zero-match result is reproducible, but this legacy rule is a weak comparator for general practice/polarity detection.

Future baselines should distinguish mention detection from permitted/denied/conditional classification, cover declared actions and evidence formats, and be developed using training/validation examples before a separate held-out evaluation.

Post-test diagnostic only. The regex, TF-IDF model and frozen predictions have not been changed or tuned.
