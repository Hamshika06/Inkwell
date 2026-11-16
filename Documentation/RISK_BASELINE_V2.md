# Actor-aware, coverage-masked risk baseline

The baseline uses the sale-v2 `risk_review` annotations in the combined
five-class corpus. It predicts **paragraph-level practice/actor/polarity triples**,
keeping sale, rental, advertising disclosure, third-party ad collection and
business transfer distinct.

The [target schema](../configs/risk_baseline_schema.json) fixes five practice
types, six actor roles and four polarity values, producing 120 binary targets.
`actor` is predicted as part of the target; it is not provided as an inference
feature. Original source verbs and recipient roles remain annotation provenance,
not inputs that would be unavailable for a new paragraph.

## Coverage and actor masking

The target builder in [inkwell/risk_baseline.py](../inkwell/risk_baseline.py)
implements the following contract:

| Annotation state | Supervision |
| --- | --- |
| Unannotated paragraph | All target masks are zero; exclude the row from vectorizer and classifier fitting |
| Practice not explicitly covered | Mask every target for that practice |
| Covered practice, no propositions | Known absence: all actor/polarity targets for that practice are negative |
| Covered practice with propositions | Supervise all four polarities for the explicitly annotated actors; mask other actors |

For example, a service provider's sale restriction gives a positive target for
`sale/service_provider/denied`. It does **not** label
`sale/first_party/denied` positive or negative: the first-party interpretation is
unknown unless a first-party proposition is also recorded, or the practice is
explicitly absent from the checked paragraph.

Checked absence relies on `covered_practice_types` meaning the practice was
checked throughout the paragraph. This assumption is explicit. Partial actor
coverage is otherwise conservative; it does not assume that an unlisted actor
was exhaustively checked. Unknown supervision is never represented as an
ordinary negative during fitting or scoring.

Repeated identical triples collapse to one paragraph target; opposing scoped
labels remain separate positives. The model does not identify those scopes or
generate evidence spans.

## Fitting and validation

The model fits word TF-IDF unigrams/bigrams on **278 supervised training
paragraphs**, excluding the other **7,101**. It then fits a balanced LinearSVC
for each target using only that target's known cells. Fixed settings are C=1,
up to 20,000 features, min_df=1, sublinear term frequency and zero decision
thresholds. There is no validation-based threshold tuning.

Targets with only one known class use explicit constant predictors. A target
with no known training supervision has no fitted predictor and returns a null
score, rather than a fabricated learned margin. If that target is positive in
known evaluation data, failure to predict it still counts as a miss.

Validation scores **48 annotated paragraphs**, excluding 1,259 unknown ones.
No test annotation file is read by the training command. The subsequent,
separate frozen-model test measurement is recorded below.

| Measure | Initial validation result |
| --- | ---: |
| Joint masked micro F1 | 0.769 |
| Macro F1 over supported, known triples | 0.375 |
| Exact match on known targets | 34 / 48 = 0.708 |
| Known validation target cells | 4,700 |
| Unknown validation target cells | 1,060 |
| First-party sale flags detected | 6 / 12 |
| False first-party sale flags | 0 / 33 known negatives |
| First-party sale-flag F1 | 0.667 |

Three additional validation paragraphs have unknown first-party sale flags and
are excluded from that binary metric. A first-party sale flag combines only
`sale/first_party/permitted` and `sale/first_party/conditional`; it does not
collapse other actors into the first party.

Rental micro F1 is 0.222 on eight positive target assignments. Business-transfer
micro F1 is 0.977 on 22. The stronger business-transfer result contributes
substantially to the overall micro score. Validation contains no positive
third-party ad-collection annotations, so its recall cannot be estimated.

These figures measure agreement with a small, selected, model-assisted
annotation set. They are not a calibrated measure of privacy harm. They also
are not directly comparable to sale-v1's different targets and coverage.

## Run artifacts and reproduction

The saved [run report](../runs/risk-actor-masked-tfidf-seed42/REPORT.md) links the
configuration to these artifacts in the same directory:

- `model.joblib`: fitted vectorizer, target-specific models and support states.
- `run.json`: source/input/schema/model/code hashes, included/excluded counts,
  per-target training supports, provenance and settings.
- `labels.json`: fixed practice/actor/polarity target order.
- `annotation_schema.json`: frozen target definitions and masking contract.
- `validation_metrics.json`: masked confusion counts and metrics by practice,
  actor and target, plus a first-party sale flag and template diagnostic.
- `validation_predictions.jsonl`: every scored paragraph's positive labels,
  predictions, masks, values, scores and nearest training template.

```sh
python -m scripts.train_risk_baseline \
  --batch data/review/sale-v2 \
  --out runs/risk-actor-masked-tfidf-reproduction \
  --seed 42
```

The loader checks source identity, complete split membership, annotation fields,
coverage, actors, labels, evidence offsets, optional original-verb spans, and
train/validation source-group and normalized-text separation. It refuses to
overwrite an existing run. A new model run does not overwrite annotations or
the source snapshot.

To infer paragraph-level triples locally:

```python
from inkwell.risk_baseline import ActorMaskedPredictor

model = ActorMaskedPredictor.load("runs/risk-actor-masked-tfidf-seed42/model.joblib")
texts = ["Our service providers are not permitted to sell personal information."]
for flags in model.predict(texts):
    print([triple for triple, hit in zip(model.triples, flags) if hit])
```

Margins are not probabilities. Constant-class sentinels are identified in run
metadata, and no matching output does not establish that a paragraph is safe.
The live risk-score engine has not been changed.

## Frozen test evaluation

The saved model was evaluated without fitting, vocabulary changes, mask changes
or threshold tuning. Of the 1,731 test records, only **77 annotated paragraphs**
had known risk targets; the other **1,654** were excluded from prediction and
metrics. Within the scored paragraphs, 7,680 target cells were known and 1,560
were unknown. The same conservative actor mask used for validation was retained.

| Measure | Test result |
| --- | ---: |
| Joint masked micro F1 | 0.656 |
| Supported-target macro F1 | 0.313 |
| Exact match on known targets | 51 / 77 = 0.662 |
| First-party sale flags detected | 6 / 15 |
| First-party sale-flag precision | 6 / 7 = 0.857 |
| First-party sale-flag recall | 0.400 |
| First-party sale-flag F1 | 0.545 |
| False first-party sale flags | 1 / 61 known negatives |

One additional actor-unknown paragraph was excluded from the first-party binary
sale metric. Practice-level masked micro F1 was 0.468 for sale, 0.471 for rental,
0.000 for advertising disclosure, 0.000 for third-party ad collection, and 0.964
for business transfer. The advertising targets had only six and two positive
assignments respectively; no correct positive predictions were made for them.
The aggregate score therefore should not be read as uniform performance across
practice types.

The [test report](../runs/risk-actor-masked-tfidf-seed42/test-masked-v1/REPORT.md)
and its directory contain masked confusion counts, subgroup results,
`test_predictions.jsonl` and `evaluation.json` with model/input/code hashes.
The original model and training-run metadata are unchanged. The evaluator
verifies the source schema checksum and semantically identical reformatted
schema snapshot separately, recording both hashes.

```sh
python -m scripts.evaluate_risk_baseline \
  --run runs/risk-actor-masked-tfidf-seed42 \
  --batch data/review/sale-v2 \
  --out runs/risk-actor-masked-tfidf-seed42/test-reproduction
```

Existing evaluation directories cannot be overwritten. These are final
measurements of this frozen model. Any subsequent revision needs a separate
evaluation protocol rather than tuning to this test result.

The report separates the 26 clause IDs previously evaluated in sale-v1 (masked
micro F1 0.667) from the other 51 annotated IDs (0.650). That distinction is
ID-based; it does not establish that the latter are independent companies or
policy templates. None of the 77 scored paragraphs reached train-fitted TF-IDF
cosine similarity 0.90 to a supervised training paragraph.

## Verification

Regression tests check actor separation, checked negatives versus unknowns,
opposing scoped labels, column-level fit supports, null unsupported predictors,
unknown-cell exclusion from metrics, unknown-word exclusion from TF-IDF,
serialization and source/annotation validation. A fixture with no test file
verifies that training and validation do not require test annotations. Adding
wholly unannotated rows leaves fitted vocabulary and predictions unchanged.
