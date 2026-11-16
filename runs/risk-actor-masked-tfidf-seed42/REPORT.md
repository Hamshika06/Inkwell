# Actor-aware, coverage-masked TF-IDF baseline

Used 278 training paragraphs; excluded 7101 wholly unknown paragraphs. Scored 48 annotated validation paragraphs; excluded 1259 unknown paragraphs.

Word TF-IDF unigrams/bigrams and balanced binary LinearSVC models predict practice/actor/polarity triples. Vocabulary is fitted only on supervised training rows, and each classifier fits only its known target cells. Thresholds are fixed at zero. No test annotations were read and no test evaluation was performed.

## Masking contract

- Unannotated rows and uncovered practice types have zero target masks.
- A covered practice with no annotated propositions is explicitly absent: all actor/polarity triples for that practice are known negatives.
- For a present covered practice, supervise all four polarities only for the explicitly annotated actors. Other actors remain unknown.
- A scoped denial is not a known negative for the same practice in another actor's role.
- Topic label masks never substitute for risk coverage. Annotation unclear is an explicit target, not missing supervision.

## Validation

| Measure | Result |
| --- | ---: |
| Joint masked micro F1 | 0.769 |
| Macro F1 over known supported targets | 0.375 |
| Exact match on known targets | 0.708 |
| Validation known target cells | 4700 |
| Validation unknown target cells | 1060 |

## Practice results (actors retained)

| Practice | Known positive support | Micro F1 | Supported-target macro F1 |
| --- | ---: | ---: | ---: |
| sale | 23 | 0.667 | 0.405 |
| rental | 8 | 0.222 | 0.125 |
| advertising_disclosure | 2 | 0.667 | 0.500 |
| third_party_ad_collection | 0 | N/A | N/A |
| business_transfer | 22 | 0.977 | 0.977 |

## First-party sale flags

The flag combines first_party sale/permitted and sale/conditional only. Vendor restrictions and other actors are not collapsed into first-party labels.

Known paragraphs: 45; unknown: 3. TP=6, FP=0, FN=6, TN=33.
Precision=1.000, recall=0.500, F1=0.667.

## Interpretation

All confusion counts and metrics exclude unknown ground-truth cells. Exact match considers only known cells on each scored row; it is not a claim of exact recovery of every actor/scope in the paragraph. Each target's confusion matrix is [[TN, FP], [FN, TP]]. Recall is null without known positive support.

0 annotated validation paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a supervised training paragraph. See validation_predictions.jsonl for nearest templates and all known/unknown targets.

- Agreement with supplied model-assisted annotations, not calibrated privacy-risk accuracy.
- Small, keyword-selected annotation subset with sparse actor/practice combinations.
- Unannotated rows are excluded; partial actor supervision is conservative and does not assume every unlisted actor is negative.
- Recall cannot be measured for any practice/actor/polarity target with zero known validation positives; see the support counts.
- Predictions are paragraph-level label sets, without extracted scope or evidence spans.
- Source-prefixed group separation is checked, but independent cross-source company/template isolation is not established.

This run changes neither annotations nor the live risk-score engine. Scores are not probabilities, and an empty prediction is not a safety judgment.
