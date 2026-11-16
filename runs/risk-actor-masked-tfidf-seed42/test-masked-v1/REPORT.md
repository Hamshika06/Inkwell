# Frozen actor-aware, coverage-masked test evaluation

Scored 77 annotated paragraphs from the 1731-record test split. Excluded 1654 wholly unannotated paragraphs. These are not metrics over the entire test population.

The saved TF-IDF vocabulary, classifiers, target order, coverage masks and zero thresholds were frozen. No fitting, retraining or threshold tuning was performed. The original trained model and training-run metadata remain unchanged.

## Masked test results

| Measure | Result |
| --- | ---: |
| Joint masked micro F1 | 0.656 |
| Supported-target macro F1 | 0.313 |
| Exact match on known targets | 0.662 |
| Known target cells | 7680 |
| Unknown target cells (excluded) | 1560 |

Exact match checks only known cells on rows with supervision, not every possible actor or scope. Each per-target confusion matrix is [[TN, FP], [FN, TP]]. Recall is undefined without known positive support.

## Practice results, with actors retained

| Practice | Known positive support | Micro F1 | Supported-target macro F1 |
| --- | ---: | ---: | ---: |
| sale | 30 | 0.468 | 0.535 |
| rental | 12 | 0.471 | 0.242 |
| advertising_disclosure | 6 | 0.000 | 0.000 |
| third_party_ad_collection | 2 | 0.000 | 0.000 |
| business_transfer | 29 | 0.964 | 0.491 |

## First-party sale flags

The binary flag combines only sale/first_party/permitted and sale/first_party/conditional. Other actors' denials are not first-party negatives.

Known paragraphs=76; actor-unknown paragraphs excluded=1. TP=6, FP=1, FN=9, TN=60.
Precision=0.857, recall=0.400, F1=0.545.

## Prior clause exposure

| Test subset | Scored paragraphs | Masked micro F1 |
| --- | ---: | ---: |
| Previously evaluated in sale-v1 | 26 | 0.667 |
| Other annotated clause IDs | 51 | 0.650 |

Other clause IDs are not necessarily independent companies or templates. Source-prefixed policy/group and exact normalized-text separation from train/validation were checked; broader company independence is not established.

0 scored paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a supervised training paragraph. The below-threshold diagnostic is in test_metrics.json.

## Limits

- The annotated test subset is small and selected; results measure agreement with supplied model-assisted annotations.
- Unknown cells remain excluded. Scores and single-class sentinels are not probabilities; an empty prediction does not mean safe.
- Predictions are paragraph-level triples, without extracted evidence spans or resolved scope.
- Keep this as the final measurement of this frozen model; later model changes require a separate evaluation protocol.

Files: evaluation.json (input/model hashes and cohort), test_metrics.json (masked confusion counts and subgroup results), test_predictions.jsonl (labels, masks, scores and individual predictions). No live risk-score integration was performed.
