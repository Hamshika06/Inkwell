# Risk scoring and sale-practice detection: progress and next steps

Status updated November 9, 2026.

## Latest implementation milestone

Schema v2 now defines `practice_type`, `scope` and `opt_outs` alongside the
existing polarity and evidence fields. The validator checks all five span lists
and distinguishes scope and opt-outs from actual conditions or exceptions.

A new `audit` command produces a structural draft report with all detected
issues, counts and schema/source hashes, without changing attribution or
creating an accepted dataset. A separate `normalize` command recovers complete
JSON objects split across physical lines and writes a new JSONL copy.

The latest training file contained one wrapped JSON object. The
[normalized copy](../data/review/sale-v1/train.normalized.jsonl) preserves all
137 records and annotation values. Its
[schema-v2 audit](../data/review/sale-v1/train.normalized.audit.json) reports zero
structural issues across 279 spans. The original draft, frozen candidate batch,
schema snapshot and held-out split files were preserved. All 23 pipeline and
annotation-tool tests passed.

## Objective

Build an explainable privacy-policy risk engine that uses detected clauses,
distinguishes permission from denial, and links every finding to exact source
evidence. The work currently includes a functioning rule-based risk baseline and
an annotated training draft for a more contextual practice/polarity detector.

## 1. Implemented risk-scoring baseline

The existing paragraph classifier assigns privacy-policy topics. A deterministic
engine in [inkwell/risk.py](../inkwell/risk.py) then checks supported wording in
paragraphs assigned to the relevant categories.

| Detected practice | Points |
| --- | ---: |
| Sale of personal data | 30 |
| Sharing with advertisers | 20 |
| Indefinite data retention | 20 |
| Do Not Track signals not honored | 15 |
| Policy changes without notice | 15 |

The score sums distinct matched rules, up to 100. Repeated clauses add evidence
without adding duplicate points. Classifier margins and logits do not enter the
risk arithmetic. Missing security, retention, choice/control and access/deletion
topics appear separately as review gaps and do not add points.

Analysis results include the score, screening band, contributing rules and exact
evidence offsets. These appear in the API response, web overview, and JSON and
Markdown exports. Clicking a finding in the web interface opens its source
paragraph.

The sale rule distinguishes supported wording such as “We may sell your personal
information” from “We will not sell your personal information.” However, its
narrow patterns do not reliably cover paraphrases, conditions, exceptions or
references to other parts of a policy. A zero score means no supported wording
matched, not that the policy is safe. Weights and screening bands remain
provisional; they are not calibrated estimates of harm.

See [RISK_SCORING.md](RISK_SCORING.md) for the scoring contract and limitations.

## 2. Recovery of original OPP-115 annotations

The previous preprocessing retained category labels and four extraction
attributes: Personal Information Type, Third Party Entity, Purpose and Retention
Period. To support polarity detection, the original OPP-115 archive was obtained
from the [Usable Privacy Policy Project](https://usableprivacy.org/data), and its
attributes were recovered for candidate segments.

The recovered data includes Does/Does Not, Action Third Party, Choice Type and
Choice Scope, along with the original annotator identifiers and selected spans.
Two source-schema details prevent a direct conversion to sale labels:

- `Does/Does Not` defaults to `Does`; that value alone does not establish an
  explicit assertion that personal information may be sold.
- `Action Third Party` has no dedicated sale value. Sharing annotations must
  therefore be interpreted with their source wording.

The exporter verifies selected spans against raw sanitized segments and maps
usable spans to the cleaned benchmark text. Offset repairs require a unique text
match. Known errant or unmatched spans remain identifiable without being exposed
as usable evidence. Source and output hashes are recorded in the batch manifest.

## 3. Candidate dataset

Searching sale-related wording across the 3,663 retained OPP-115 segments produced
**182 candidate segments from 100 policies**. Selection did not depend on the
paragraph's topic label. Existing frozen policy/company splits were preserved.

| Split | Candidate segments | File |
| --- | ---: | --- |
| Training | 137 | [train.jsonl](../data/review/sale-v1/train.jsonl) |
| Validation | 18 | [validation.jsonl](../data/review/sale-v1/validation.jsonl) |
| Test | 27 | [test.jsonl](../data/review/sale-v1/test.jsonl) |

The [candidate snapshot](../data/review/sale-v1/candidates.jsonl) retains source
records and attributes. The [training queue](../data/review/sale-v1/REVIEW.md)
provides a readable view of the clauses and original annotations.

Keyword selection also captures product sales, sales staff and corporate asset
transfers. It can miss implicit sale practices and paraphrases. Consequently,
this batch is a starting dataset rather than a complete benchmark for measuring
general sale-detection recall.

## 4. Current annotation draft

[train.reviewed.jsonl](../data/review/sale-v1/train.reviewed.jsonl) contains an
AI-generated annotation draft covering all 137 training candidates. It records
whether a candidate is sale-related and represents distinct propositions with
practice type, polarity, exact evidence, scope, conditions, exceptions, opt-outs
and explanatory notes.

The four polarity labels are:

| Label | Meaning |
| --- | --- |
| `permitted` | Sale is stated or allowed within the recorded scope. |
| `denied` | Sale is explicitly ruled out within the recorded scope. |
| `conditional` | Permission depends on a stated condition, or an exception qualifies a denial. |
| `unclear` | The sale interpretation remains ambiguous in the available context. |

Practice type separates what is being discussed from its polarity:

| Practice type | Entries in the current draft |
| --- | ---: |
| `sale` | 63 |
| `business_transfer` | 51 |
| `aggregate_sale` | 4 |
| `recipient_onward_sale` | 4 |
| `data_broker_relationship` | 1 |
| **Total** | **123** |

These counts describe propositions, not paragraphs. A candidate can contain
multiple propositions or be rejected as unrelated. Across the 123 entries,
72 are labelled conditional, 34 denied, 11 permitted and 6 unclear.

The annotation iterations corrected several recurring interpretation issues:

- Purpose-limited denials retain their scope instead of becoming conditional
  permissions merely because other purposes are not addressed.
- Opt-outs are recorded separately from consent prerequisites.
- Sharing permissions are kept separate from sale permissions.
- Current denials and possible future practices can be represented separately.
- Ambiguous interpretations carry practice-level explanations.

The latest structural checks confirmed valid JSONL, unique IDs, complete training
coverage, unchanged source records, valid polarity labels and exact offsets for
all **279 spans**, including scope and opt-out spans. Structural consistency does
not establish the accuracy of every interpretation.

## 5. Tooling and remaining implementation work

[scripts/sale_review.py](../scripts/sale_review.py) exports candidate batches and
validates annotation structure, source integrity, labels and evidence offsets.
Tests cover span mapping, unique repairs, unusable spans, export, provenance and
invalid annotation cases.

Schema v2 formalizes `practice_type`, `scope` and `opt_outs`, with corresponding
validator coverage and a separate draft-audit workflow. Ambiguous cross-references
still need consistent treatment. For example, a qualified denial followed by
permission under specified circumstances is not automatically a contradiction.

The contextual practice/polarity model has not yet been trained or integrated.
The live risk engine continues to use the original deterministic rules. Risk
weights will need a separate evaluation from practice-detection accuracy.

## 6. Next plan of action

1. **Finalize the schema and guidelines.** Resolve ambiguous cases and update the validator.
2. **Review the remaining training records**, then annotate validation data using the same guidelines. Keep test data sealed.
3. **Train a baseline** to predict practice type and polarity. Evaluate `sale` separately from business transfers and aggregate-data sales.
4. **Measure validation performance:** per-label precision/recall, confusion matrix, and especially false sale accusations. Compare against the regex engine.
5. **Fix recurring errors** using training and validation data. Add examples if some labels have too little support.
6. **Evaluate once on the held-out test set** after freezing the model and decision rules.
7. **Integrate the detector into risk scoring**, showing evidence and uncertain results for review.

The next deliverable is an evaluated practice/polarity detector with traceable
evidence. Its evaluation should distinguish errors in topic classification,
practice interpretation and policy-level scoring.
