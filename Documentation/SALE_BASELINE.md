# TF-IDF practice/polarity baseline

The first baseline is trained in
[runs/sale-tfidf-seed42](../runs/sale-tfidf-seed42/REPORT.md).
It uses 137 annotated training paragraphs and evaluates 18 validation paragraphs.
Training used no test data or threshold tuning. A subsequent frozen-model test
evaluation is recorded below. The live risk engine is unchanged.

## Frozen test results: official 26-record cohort

The user changed the sale-test cohort from 27 source candidates to the 26
annotated records currently in `test.jsonl`, before test predictions were
computed. The versioned [test cohort](../data/review/sale-v1/test_cohort.json)
defines the official membership and excludes `opp115:1618#0021`. The original
candidate snapshot remains available for provenance; training and validation
membership are unchanged.

The saved TF-IDF vocabulary, classifiers, label order and zero thresholds were
used without fitting or tuning:

| Measure | Test result |
| --- | ---: |
| Joint practice/polarity micro F1 | 0.737 |
| Joint macro F1 over supported labels | 0.631 |
| Exact paragraph label-set matches | 20 / 26 |
| Practice-type micro F1 | 0.857 |
| First-party sale-flag precision | 5 / 5 = 1.000 |
| First-party sale-flag recall | 5 / 8 = 0.625 |
| First-party sale-flag F1 | 0.769 |
| False sale flags | 0 / 18 negative paragraphs |

The regex baseline detects none of the eight annotated positive sale flags.
This is the legacy exact-wording risk rule, not a general regex practice/polarity
baseline; see the diagnostic below before interpreting that comparison.
The full [test report](../runs/sale-tfidf-seed42/test-26-v1/REPORT.md) includes
metrics by practice type. That directory also contains confusion matrices,
individual predictions, the declared cohort, and model/input hashes.

The evaluator checks exact cohort coverage, frozen inputs, source identity and
train/validation separation. Existing evaluation directories are not overwritten:

```sh
python -m scripts.evaluate_sale_baseline \
  --run runs/sale-tfidf-seed42 \
  --out runs/sale-tfidf-seed42/test-26-reproduction
```

These are the final test measurements for this saved model on the declared
cohort. The sample is small and keyword-selected; results measure agreement with
the supplied annotations. Subsequent model changes need a separate evaluation
protocol rather than tuning to this test result.

## Regex comparator diagnostic

The [post-test audit](../runs/sale-tfidf-seed42/test-26-v1/regex-audit/REPORT.md)
recomputed both flags from all 26 original paragraphs and matched records by ID
and exact text. It found zero stored-flag mismatches. Synthetic controls confirm
that supported affirmative phrases match and denials do not.

The legacy pattern is:

```regex
\bwe\s+(?:(?:may|will|do)\s+)?sell\s+(?:your\s+)?(?:personal\s+)?(?:data|information)\b
```

`regex_sale_flag` means an affirmative match to this pattern. It does not mean
sale was mentioned. `source_category_gated_regex_sale_flag` additionally requires
the original Third Party Sharing/Collection category. Therefore:

- “We do not sell your personal information” is intentionally false.
- “We may sell your personal information” is true for the ungated rule.
- Quoted “rent,” marketing-list objects, coordinated verbs, named company
  subjects and richer conditional constructions fall outside this pattern.

The two Zacks test records include both `sale/permitted` and `sale/denied` labels,
with rental treated as permitted in the supplied annotations. The legacy rule
does not recognize rentals, so action definitions also limit this comparison.
This is not evidence of a joining bug, but it makes the comparator inadequate
as a general rule-based sale detector. The zero-match figure is reproducible;
it should not support a broad claim that TF-IDF outperforms regex approaches.

The diagnostic does not change the rule, annotations, model or frozen results.
A stronger rule baseline should distinguish mention detection from polarity,
declare its sale/rental scope, and be developed using training/validation data
before a separate held-out evaluation.

```sh
python -m scripts.audit_sale_regex \
  --predictions runs/sale-tfidf-seed42/test-26-v1/test_predictions.jsonl \
  --source data/review/sale-v1/test.jsonl \
  --out /tmp/inkwell-regex-audit
```

## Model and targets

Word TF-IDF unigrams and bigrams feed balanced binary LinearSVC classifiers,
one for each schema-v2 practice/polarity pair. Features are fitted on training
paragraph text only. Annotations, evidence offsets, topic labels and record IDs
are not model inputs. Hyperparameters are fixed: C=1, min_df=1, up to 20,000
features, sublinear term frequency and a decision threshold of zero.

A paragraph can have multiple targets. For example, a denial for newsletter
data and permission to sell postal-address lists remain distinct labels.
Repeated identical practice/polarity pairs collapse to one paragraph target.
The training draft has 123 propositions corresponding to 122 distinct
paragraph/pair assignments. The model does not locate individual propositions
or extract supporting evidence, conditions or exceptions.

Practice types distinguish first-party personal-information sales from business
transfers, aggregate-data sales, recipient restrictions and broker relationships.
Pairs absent from training always predict negative; their fixed -1 score is
a sentinel rather than a learned margin. Other scores are uncalibrated SVM
decision margins.

## Initial validation results

| Measure | Result |
| --- | ---: |
| Joint practice/polarity micro F1 | 0.897 |
| Joint macro F1 over supported labels | 0.786 |
| Exact paragraph label-set matches | 16 / 18 |
| Practice-type micro F1 | 0.929 |
| First-party sale-flag precision | 3 / 3 = 1.000 |
| First-party sale-flag recall | 3 / 5 = 0.600 |
| First-party sale-flag F1 | 0.750 |
| False sale flags | 0 / 13 negative paragraphs |

The binary sale flag combines `sale/permitted` and `sale/conditional`.
Business transfers and other contextual practice types are negative for that
target. The existing data-sale regex detects none of the five reference-positive
paragraphs, both without a category gate and with the original source topic gate.
That comparison measures the narrow regex against the same target; it is not a
comparison of full-policy risk scores.

The two paragraphs with label-set errors are `opp115:1050#0011` (conditional
sale wording) and `opp115:414#0008` (different permissions for newsletter versus
postal-address data). The model predicts no pairs for either paragraph.

These results measure agreement with the supplied annotations, which include
AI-authored drafts. The validation set is small and keyword-selected, contains
no `unclear` examples, and is not representative of all privacy clauses. One
validation paragraph has train-fitted TF-IDF cosine similarity >= 0.90 to a
training paragraph. On the remaining 17 paragraphs, joint micro F1 is 0.889.
Zero observed false flags does not establish a zero error rate on new policies.

## Reproduce and inspect

From the project root, with the research dependencies installed:

```sh
python -m scripts.train_sale_baseline --out runs/sale-tfidf-reproduction --seed 42
```

The command refuses to overwrite a run. It checks schema-v2 annotations, complete
candidate coverage, source integrity and disjoint policy/company/normalized-text
splits before fitting. The test file is not supplied to fitting, inference or
evaluation.

Artifacts in each run:

- `model.joblib`: fitted vectorizer, classifiers and target-pair order.
- `run.json`: input/schema/model hashes, label support, configuration, provenance
  and software versions.
- `labels.json` and `annotation_schema.json`: target definitions.
- `validation_metrics.json`: per-label precision/recall/F1 and confusion matrices
  ordered `[[TN, FP], [FN, TP]]`, plus separate practice-type and sale-flag results.
- `validation_predictions.jsonl`: each reference/predicted label set, margin,
  regex result and nearest training template.
- `REPORT.md`: readable results and limitations.

Recall is null for labels without validation support. Macro F1 includes only
labels with positive validation support; micro F1 also counts false predictions
for unsupported labels.

For local inference on paragraphs:

```python
from inkwell.sale import SalePredictor

model = SalePredictor.load("runs/sale-tfidf-seed42/model.joblib")
texts = ["We may sell your personal information."]
predicted = model.predict(texts)
for text, flags in zip(texts, predicted):
    print(text, [pair for pair, hit in zip(model.pairs, flags) if hit])
```

Validation identified missed conditional and mixed-scope examples. The frozen
baseline has now received its test evaluation. Any future improvement should
retain these measurements and define a separate final evaluation protocol.
