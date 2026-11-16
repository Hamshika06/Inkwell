# Sale-v2: GoPPC source schema and risk-engine proposal

## Current snapshot

The requested file is copied byte-for-byte to [goppc_train.jsonl](goppc_train.jsonl).
It contains **6,250 paragraphs from 117 policy IDs and 117 website values**.
All rows have source `goppc` and source split `train`. No annotations, labels,
text or metadata were changed, and no new model was trained.

[manifest.json](manifest.json) records source/copy hashes and the analysis inputs.
[schema_profile.json](schema_profile.json) records the schema, counts and quality
checks. The original sale-v1 dataset, model and evaluation are separate artifacts.

## What the source schema provides

| Field | Contents | Proposed use |
| --- | --- | --- |
| `source` | `goppc` | Dataset provenance |
| `unit_id` | Unique paragraph ID, such as `goppc:train:105` | Preserve as the new review record's ID |
| `doc_id`, `group_id` | Reconstructed policy IDs, such as `goppc:2` | Policy grouping; validate company identity before splitting |
| `text` | Paragraph text | Model input and reference text for new evidence offsets |
| `labels` | One or more of five broad topic labels | Topic routing, not risk points or polarity |
| `label_mask` | Five positional known/unknown indicators | Preserve the source value; derive corrected masks separately |
| `spans` | Empty in every row | No source evidence spans are available |
| `split` | `train` in every row | Preserve as `source_split`; derive evaluation membership separately |
| `orig_label` | Semicolon-separated annotator concept lists | Rebuild topic agreement and retain disagreement |
| `orig_concepts` | Union of original concept IDs | Candidate routing and annotation provenance |
| `metadata.website` | Website name | Check and normalize company grouping |
| `metadata.parents`, `metadata.siblings` | Related source text | Optional context after checking its association with the paragraph |
| `metadata.parents_matrix`, `metadata.siblings_matrix` | Encoded annotation metadata | Exclude from model features |
| `metadata.numeric_columns_uninterpreted` | Copied numeric source columns | Preserve; exclude from model features until their semantics are established |

The five topics have the following positive counts. Counts overlap because the
task is multi-label:

| Topic | Positive rows |
| --- | ---: |
| Data Collection & Use | 2,670 |
| Data Sharing | 1,008 |
| User Rights & Choices | 1,639 |
| Data Security & Retention | 636 |
| Policy Scope & Changes | 498 |

There are 969 rows with no mapped positive topic. This does not establish that
they have no risky practice. The file does **not** contain practice polarity,
risk severity, sale/rental distinctions or a validated numeric risk target.

## Issues to resolve before using this as supervised risk data

1. **Rebuild topic labels and masks from original annotation groups.** Every
   source mask is `[1, 1, 1, 1, 1]`. Recomputing with the current
   [GoPPC mapper](../../../../configs/goppc_mapping.json) changes labels on 343 rows
   and masks on 1,053 rows. The source conversion unions concepts across
   annotators; the later mapper uses majority agreement, concept repairs and
   unknown masks. These differences include mapping changes as well as
   disagreement handling. Keep the source copy intact and write derived fields
   to a separate review file.
2. **Retain unknown supervision.** 1,028 rows contain NON-GDPR/UNKNOWN concepts.
   An unknown topic or risk label must not become a negative training example.
3. **Address repeated text before splitting.** There are 63 normalized duplicate
   groups, with 77 extra rows; 46 groups span multiple policies. Template-level
   leakage checks are needed in addition to policy grouping. Also inspect the
   100 paragraphs under five words and 44 over 300 words rather than truncating
   away conditions or exceptions.
4. **Check provenance of policy grouping.** The preprocessing code reconstructs
   policy IDs using phrase matches and neighboring rows. The existing GoPPC
   preprocessing report says all 6,250 rows lack IDs, while this snapshot has
   none missing. That report is stale for this file and cannot verify the
   current assignments.
5. **Keep encoded annotations out of features.** Original concept IDs, labels,
   masks and matrices can leak target information. Textual parent/sibling
   context may be useful, but it must be available at inference and remain in
   the same policy split.

## Proposed design: topic routing, practice interpretation, then scoring

Use the same paragraph text for both tasks, but keep their targets distinct:

```text
GoPPC paragraph + optional source context
    -> five-topic routing
    -> practice + polarity + scope/conditions/exceptions/choices + evidence
    -> explicit practice-specific risk rubric
    -> score contribution and source-linked explanation
```

A Data Sharing topic does not imply sale, and a Data Security & Retention topic
does not establish secure storage or indefinite retention. The current live
engine uses ten OPP-115 categories, so the five GoPPC labels cannot be passed
straight into its category gates. Use a topic adapter for routing; retain
original concept IDs to distinguish merged topics where possible. They do not
provide the missing polarity or risk targets.

### Proposed review fields

Create a separate `risk.review.jsonl`, preserving the source snapshot. Each
record should contain:

- Stable `id` from `unit_id`, plus source hash/reference, `doc_id`, company group,
  exact `text` and website.
- `source_split`, `source_topic_labels` and `source_topic_mask`, unchanged from
  the copied file.
- Derived `split`, `topic_labels` and `topic_label_mask`, with mapper version and
  a record of any repair. Do not overwrite source values with derived values.
- `review.status`: `unannotated` or `annotated`; an empty unannotated practice
  list is unknown rather than evidence of no risk.
- `review.practices`: each with `practice_type`, `label`, `evidence`, `scope`,
  `conditions`, `exceptions`, `opt_outs` and `notes`.
- Annotation author/origin and schema version, preserved separately from model
  predictions.

Retain `permitted`, `denied`, `conditional` and `unclear` as interpretation labels.
Apply them to the named practice and actor. Keep business transfers, aggregate
data and recipients' onward sales distinct from ordinary first-party sale.
**Add rental as its own practice type** so a statement that permits list rental
and denies sale can be represented without contradictory action definitions.

First implement sale, rental and advertiser sharing, then extend to indefinite
retention, honoring Do Not Track signals and changes without notice. Related
rights/security topics can be added as explicitly defined protective or adverse
practices. Broad collection, transfer or audience topics alone should not add
points. For practices such as honoring DNT, a denial has a different scoring
direction from denying data sale; scoring must be practice-specific.

For example, `goppc:train:105` has topic Data Sharing but contains this exact span:

```json
{
  "practice_type": "sale",
  "label": "denied",
  "evidence": [{
    "start": 243,
    "end": 310,
    "text": "We don't sell any of your information to anyone, and we never will."
  }],
  "scope": [],
  "conditions": [],
  "exceptions": [],
  "opt_outs": [],
  "notes": "Illustrative interpretation of this span, not an annotation written into the dataset."
}
```

Offsets refer to the unchanged paragraph `text`, not the parent or sibling text.
Evidence concerning more than one contextual paragraph needs explicit source
references rather than fabricated offsets.

## Proposed next actions

1. **Prepare the derived review adapter.** Reuse the current mapper's label,
   agreement and mask logic. Add stable IDs and empty risk-review fields without
   inventing polarity or numeric scores. Keep topic masks separate from risk
   annotation status.
2. **Reuse policy-level train/validation membership.** The existing cleaned
   five-class file identifies 100 training policies and 17 validation policies
   for this source. Reuse that partition after checking its grouping provenance
   and duplicates; do not randomly split paragraphs. Its cleaned rows retain
   4,255 source training IDs and 772 validation IDs, so join by policy and
   lineage rather than assuming a one-to-one row match. Do not import the
   separate GoPPC test file into this training snapshot.
3. **Build a risk-practice annotation batch.** Start with sharing/sale/rental
   clauses, include denials, consent, exceptions and unrelated product sales,
   and add independently sampled paragraphs without sale keywords. The 217
   sale/rental keyword matches are retrieval candidates, not final labels.
4. **Freeze the expanded practice schema and scoring rubric.** Define whether
   rental contributes separately, how conditions affect contributions, and how
   protective practices are represented. Keep missing/unknown evidence distinct
   from zero risk. Do not learn severity from the five topic labels.
5. **Train and compare on the new targets.** Use full paragraph text with masked
   unknown targets. Compare against baselines that share the same action and
   polarity definitions. Evaluate sale separately from rental and corporate
   transfers. Reserve final evaluation for a separately declared cohort with
   policy/company and template separation.
6. **Integrate the interpreted practices into scoring.** Use distinct practice
   contributions, source-linked evidence and explicit uncertainty. Preserve the
   original rule engine as a reference until the new targets and rubric have
   been evaluated.

The immediate implementation should be the **GoPPC-to-risk-review adapter**, not
another training run or direct topic-to-risk weighting. That adapter is proposed
here; it has not yet been applied to the copied source.
