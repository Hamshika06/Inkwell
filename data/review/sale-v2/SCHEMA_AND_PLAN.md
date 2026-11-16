# Sale-v2: combined five-class source and risk-engine proposal

## Active source

Use [combined_classifier.jsonl](combined_classifier.jsonl), copied byte-for-byte
from `data/final_combined_fivecls_data/combined_classifier.jsonl`.
It replaces the earlier GoPPC-only source for this work. The previous source and
proposal are archived in [prior_goppc_source](prior_goppc_source/SCHEMA_AND_PLAN.md).

The active file has **10,417 paragraphs from 293 source-prefixed policy IDs**,
with existing training, validation and test assignments:

| Source | Train | Validation | Test | Total |
| --- | ---: | ---: | ---: | ---: |
| OPP-115 | 2,666 | 433 | 341 | 3,440 |
| PolicyIE | 518 | 102 | 157 | 777 |
| GoPPC | 4,195 | 772 | 1,233 | 6,200 |
| **Total** | **7,379** | **1,307** | **1,731** | **10,417** |

There are 213 policy IDs in training, 32 in validation and 48 in test.
Preserve these assignments. The earlier suggestion to create a 100/17-policy
partition applied to the superseded GoPPC-only file, not this combined dataset.

The [manifest](manifest.json) records hashes and the source replacement.
[schema_profile.json](schema_profile.json) contains independently checked counts
and consistency checks. [upstream_manifest.json](upstream_manifest.json) preserves
the supplied combined dataset's class order, counts and processing report.
No model was trained, and the original source file was not modified.

The split-specific risk-review templates are now prepared:
[train.jsonl](train.jsonl), [validation.jsonl](validation.jsonl) and
[test.jsonl](test.jsonl). They retain every source field and add empty
`risk_review` objects. See [REVIEW_FORMAT.md](REVIEW_FORMAT.md) and
[review_manifest.json](review_manifest.json). Seed import, expanded schema
validation and risk-model training remain separate next steps.

## Source schema

| Field | Meaning | Risk-engine use |
| --- | --- | --- |
| `id` | Stable, source-prefixed paragraph ID | Keep unchanged; use for annotation joins |
| `source` | `opp115`, `policyie` or `goppc` | Provenance and per-source evaluation |
| `doc_id` | Source-prefixed policy ID | Preserve policy boundaries |
| `group_id` | Group ID; currently matches policy ID | Retain; check cross-source company identity separately |
| `split` | `train`, `validation` or `test` | Preserve existing partition |
| `text` | Exact paragraph text | Model input and reference for evidence offsets |
| `labels` | Positive five-class topic names | Topic routing; not severity or polarity |
| `label_vec` | Five positional binary topic labels | Topic-classification supervision |
| `label_mask` | Five positional known/unknown indicators | Ignore mask-zero targets in topic loss and metrics |
| `meta` | Source-specific original labels, concepts or lineage | Provenance and possible enrichment; not automatic model features |

The class order is fixed by the upstream manifest:

1. Data Collection & Use
2. Data Sharing
3. User Rights & Choices
4. Data Security & Retention
5. Policy Scope & Changes

`meta` differs by source:

- OPP-115 retains original categories, category fractions and some merged IDs.
- PolicyIE retains original categories/masks and parent/chunk identifiers.
- GoPPC retains raw concept labels, annotator concept groups and website names.

The combined file has no top-level practice annotations or evidence spans.
Source-specific attributes absent from `meta` must be recovered from the source
artifacts if needed. The raw GoPPC field names `unit_id` and `metadata` do not
apply to this shared schema; use `id` and `meta` instead.

## Checks and implications

Independent checks passed for unique IDs, five-entry binary vectors/masks,
agreement between labels and vectors, no positives on masked classes, policy and
group separation across splits, no normalized exact duplicate text, and upstream
row/source-split counts.

**847 rows contain unknown topic targets** and **1,291 rows have no positive
topic label**. Preserve masks: an unknown target is not negative, and no topic
label does not establish that a paragraph has no risky practice. Unlike the
previous raw GoPPC file, this input already contains the combined pipeline's
label vectors and selective masks. Do not blindly reapply the earlier raw-file
343-label/1,053-mask correction counts to this dataset.

The upstream manifest reports a passed near-copy check. That slower check was
not independently rerun for this schema inspection. Source-prefixed group IDs
also do not prove that the same company cannot appear under another source's
policy ID. Company identity and templates remain relevant when declaring an
evaluation cohort for the new risk task.

## Proposed risk-review adapter

Keep the copied classifier data as an immutable source snapshot. Create a
separate `risk.review.jsonl` with the same source fields and a new `risk_review`
object. Do not overwrite topic labels with risk labels.

Proposed initial structure:

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

This is a design proposal, not an additional annotation written into the source.
`covered_practice_types` distinguishes practices explicitly checked from those
not yet annotated. A practice absent from an unannotated or partially covered
record must remain unknown instead of becoming a negative training target.

Each populated practice should have:

- `practice_type`, plus the actor or role to distinguish company actions from
  recipient restrictions.
- `label`: `permitted`, `denied`, `conditional` or `unclear`, interpreted within
  the named practice and scope.
- `evidence`, `scope`, `conditions`, `exceptions` and `opt_outs`, with exact
  zero-based, end-exclusive offsets into the unchanged paragraph text.
- Explanatory notes and annotation provenance, separate from model predictions.

Start with sale, rental and advertising sharing. Keep sale and rental separate,
and distinguish business transfers, aggregate data and recipients' onward sale.
Then extend to retention, honoring DNT and policy-change notification. Merged
topics such as Data Security & Retention need finer practice labels before they
can support a score contribution.

## Reuse of sale-v1 annotations

Joining by canonical ID and merged-ID lineage found:

| Earlier annotation set | Found in combined split | Exact paragraph text |
| --- | ---: | ---: |
| 137 training records | 131 in train | 130 |
| 18 validation records | 18 in validation | 18 |
| 26 test records | 26 in test | 26 |

Six old training records are absent, and one matched training ID has different
text. The exact-text annotations are candidate seeds, with their original
authors and provenance retained. The mismatching record needs span remapping or
fresh annotation; copying its old offsets would be invalid. Do not fill absent
annotations with predictions and present them as reference labels.

The combined test pool contains the 26 clauses already evaluated in sale-v1.
It must not be described as an entirely fresh risk-test set. Record this prior
exposure and declare an independent evaluation subset or new policy cohort
before claiming new generalization results. Do not move those clauses into
training just to increase annotation counts.

## Recommended sequence

1. **Build the combined-data adapter.** Preserve `id`, `source`, policy/group,
   split, text, topic vectors/masks and `meta`; add empty risk-review fields.
   Require source checksum and evidence-offset validation.
2. **Import compatible seed annotations.** Join sale-v1 entries by ID/lineage,
   exact text and split. Track imports, missing rows and mismatches explicitly.
   Adopt the expanded action definitions rather than treating rental as sale.
3. **Expand practice annotations within training.** Use the five topics for
   candidate routing, with coverage outside keyword hits as well. Topic labels
   identify subjects; they do not establish permission, harm or severity.
4. **Keep annotation and model targets separate.** Apply topic masks to the
   topic task and new practice-coverage masks to the risk-practice task. Do not
   use original labels, concepts or annotation metadata as text-model features.
5. **Evaluate practice and polarity on validation.** Report performance by
   source and practice type, including missed sales and false flags. Align the
   action scope and target definition of learned and rule baselines. Preserve
   the existing splits; account for cross-source company/template overlap and
   prior test exposure when defining final evaluation.
6. **Add a practice-specific scoring rubric.** Map interpreted practices to
   explicit contributions with source evidence. A denied sale and denied DNT
   honoring have different scoring directions. Missing or unknown evidence
   remains distinct from a zero-risk finding. The five topic labels themselves
   are not numeric risk targets.

The immediate deliverable is the **combined-five-class-to-risk-review adapter**
and a validated import report for existing annotations. Training the risk model
comes after the new practice targets are available; copying this dataset alone
does not create them.
