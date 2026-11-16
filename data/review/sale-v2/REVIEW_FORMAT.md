# Sale-v2 risk-review files

The latest training expansion contains 1,126 annotated paragraphs and 709
practice propositions, with 6,253 paragraphs still unannotated. Validation
remains at 48 annotated paragraphs. See
[EXPANDED_TRAINING_AUDIT.md](EXPANDED_TRAINING_AUDIT.md) for current coverage and
the remaining validation gap. Earlier counts below describe prior versions.

The files retain the combined dataset's original splits:

| File | Records |
| --- | ---: |
| [train.jsonl](train.jsonl) | 7,379 |
| [validation.jsonl](validation.jsonl) | 1,307 |
| [test.jsonl](test.jsonl) | 1,731 |
| **Total** | **10,417** |

Each line is one complete JSON object. All source fields are unchanged:
`id`, `source`, `doc_id`, `group_id`, `split`, `text`, `labels`, `label_vec`,
`label_mask` and `meta`. Only this `risk_review` object has been added:

```json
{
  "status": "unannotated",
  "covered_practice_types": [],
  "practices": [],
  "annotation_origin": null,
  "author_id": "",
  "notes": ""
}
```

## Filling the fields

- `status`: leave `unannotated` until a practice check has been completed; use
  `annotated` when recording its results. Status alone does not establish
  complete coverage of all practice types.
- `covered_practice_types`: name the practices explicitly checked. Unlisted
  types remain unknown. A checked practice can be absent without an invented
  evidence span.
- `practices`: list the scoped propositions supported by the paragraph. Keep
  sale, rental, advertising sharing and business transfers distinct.
- `annotation_origin`: record the actual origin, such as `manual`,
  `model_assisted` or `imported`.
- `author_id`: identify the author or model responsible for the annotation.
- `notes`: explain exclusions, ambiguity, conflicts or source references.

A populated practice should contain `practice_type`, `actor`, `label`,
`evidence`, `scope`, `conditions`, `exceptions`, `opt_outs` and `notes`.
Polarity labels are `permitted`, `denied`, `conditional` or `unclear`.
Each span uses `start`, exclusive `end`, and exact `text` matching the source
paragraph's `text[start:end]`. Preserve source text while annotating.

Current practice types are `sale`, `rental`, `advertising_disclosure`,
`third_party_ad_collection` and `business_transfer`. Advertising disclosure and
direct third-party collection are separate targets. Optional `verbs` lists use
the same span format. Optional `recipient` lists contain party-role strings;
they are distinct from the `actor` field.

The current draft uses `actor` values `first_party`, `service_provider`,
`third_party_ad_network`, `third_party_advertiser`, `bankruptcy_court` and
`data_reseller`. Preserve that field; a restriction on a recipient is not a
statement about first-party permission. Actor/operation coverage must be
specified when building model targets.

The latest files contain 278 annotated training paragraphs, 48 validation
paragraphs and 77 test paragraphs, with 454 practices and 1,430 verified spans
including original verbs. See [SPLIT_ANNOTATION_AUDIT.md](SPLIT_ANNOTATION_AUDIT.md)
for the current counts, checks and coverage limits. The earlier training-only
audit records a prior annotation version.

The [actor-aware target schema](../../../configs/risk_baseline_schema.json) and
[training/validation loader](../../../scripts/train_risk_baseline.py) now support
these records, including coverage masks, actors, recipients and optional verb
spans. See [the baseline documentation](../../../Documentation/RISK_BASELINE_V2.md)
for the masking contract and initial validation results. The sale-v1 validator
reads `review`, not `risk_review`; do not use its trainer unchanged.

## Source and evaluation boundaries

Topic labels and masks remain topic supervision. They are not risk labels,
risk coverage masks or numeric scores. An empty unannotated practice list means
unknown, not safe or negative.

[review_manifest.json](review_manifest.json) records initial output hashes,
counts, source identity and the default review structure. It identifies the
26 test clauses previously evaluated in sale-v1; this test pool is not an
entirely fresh independent risk evaluation set. No previous annotations or
model predictions were imported into these templates.

The unchanged [combined source](combined_classifier.jsonl) remains the reference.
See the [schema and plan](SCHEMA_AND_PLAN.md) for the proposed practice model,
seed-import checks and scoring design.
