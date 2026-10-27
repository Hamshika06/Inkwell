# Clause-based risk screening

Every `analyze()` result, including the API's `POST /analyze` response, now includes
`risk`. The web overview shows the score, contributing findings and clickable
source evidence. JSON and Markdown exports include the breakdown.

This is an experimental, deterministic baseline. It screens for five explicit
practices in already-classified paragraphs. Topic presence alone does not add
risk: “we do not sell your data” and “we sell your data” can both be classified
as Third Party Sharing/Collection, but only the latter matches the sale rule.
Classifier margins/logits are not used as risk probabilities or weights.

| Rule ID | Required category | Points | Example matching wording |
| --- | --- | ---: | --- |
| `data_sale` | Third Party Sharing/Collection | 30 | We may sell your personal information |
| `advertising_sharing` | Third Party Sharing/Collection | 20 | We share your data with advertising partners |
| `indefinite_retention` | Data Retention | 20 | We retain personal data indefinitely |
| `dnt_not_honored` | Do Not Track | 15 | We do not respond to Do Not Track signals |
| `changes_without_notice` | Policy Change | 15 | We may change this policy without notice |

`score = sum(points for distinct matched rules)`, with a fixed maximum of 100.
Repeated matches add evidence, not points. One paragraph can support multiple
distinct practices. Matching is case insensitive and permits whitespace changes.
Rules and weights live in `inkwell/risk.py`; change the reported version when
changing scoring behavior.

Bands are provisional screening labels: 0 is `no_matches`, 1–24 `low`, 25–49
`moderate`, and 50–100 `high`. These thresholds and weights are product choices,
not estimates learned from annotated risk outcomes. **Zero does not mean safe.**

Security, retention, choice/control and access/edit/deletion categories with no
classified evidence appear in `review_gaps`. Gaps do not add risk points, since
the classifier may have missed them. Finding a clause for one of these topics
does not establish adequate protection, and protective wording does not cancel
an adverse finding elsewhere.

Example additive response field:

```json
{
  "risk": {
    "version": "1.0.0",
    "score": 30,
    "max_score": 100,
    "band": "moderate",
    "findings": [{
      "rule_id": "data_sale",
      "category": "Third Party Sharing/Collection",
      "title": "Sale of personal data",
      "points": 30,
      "evidence": [{
        "segment_id": 0,
        "start": 0,
        "end": 26,
        "text": "We sell your personal data"
      }]
    }],
    "review_gaps": ["Data Security", "Data Retention", "User Choice/Control", "User Access, Edit and Deletion"],
    "limitation": "Experimental wording-based screening ..."
  }
}
```

Evidence uses the same zero-based Python character offsets as Stage 1; `end` is
exclusive. It quotes the matched wording, and `segment_id` links to the full
paragraph so readers can inspect qualifications and exceptions.

## Limits and evaluation

The first version intentionally covers narrow English wording. Paraphrases,
passive voice, legal exceptions, conditional language, quoted examples and
contradictions need human review. A classifier false negative also prevents a
rule from firing. This is not a legal compliance judgment, a calibrated harm
probability, or a complete measure of privacy risk.

Before relying on the score for rankings, annotate a separate set of policies
with practice-level positive/negative judgments and evidence spans. Measure
precision and recall per rule, including paraphrases, negations, exceptions and
contradictions. Evaluate both gold-category inputs and predicted categories to
separate rule errors from classifier errors. Have independent reviewers assign
policy-level risk ratings to evaluate weights/bands; keep that evaluation set
separate from tuning. Existing classifier F1 does not validate the risk score.

```sh
python -m unittest discover -s tests -v
```

Tests cover exact evidence offsets (including Unicode), category gating,
protective wording, repetition, empty inputs, mixed statements and integration
with the analysis pipeline.
