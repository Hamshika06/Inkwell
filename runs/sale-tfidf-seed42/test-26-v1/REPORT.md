# Frozen TF-IDF test evaluation

Official cohort: **test-26-v1**, 26 annotated paragraphs, selected from 27 original source candidates before test predictions were computed.

User requested changing the sale-test cohort from the original 27 candidates to the 26 annotated records currently in test.jsonl.

Excluded original ID: opp115:1618#0021. The original candidate snapshot is retained for provenance. This report evaluates the declared cohort.

The saved model, TF-IDF vocabulary, label order and zero thresholds were frozen. No fitting, retraining or threshold tuning was performed.

## Results

| Task | Micro F1 | Supported-label macro F1 | Exact label-set match |
| --- | ---: | ---: | ---: |
| joint | 0.737 | 0.631 | 0.769 |
| practice_type | 0.857 | 0.908 | 0.846 |

## First-party sale flags

A positive flag means sale/permitted or sale/conditional in the reference annotation. Business transfers and other contextual practices do not count as ordinary first-party sale flags.

| Method | Precision | Recall | F1 | TP | FP | FN | TN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TF-IDF | 1.000 | 0.625 | 0.769 | 5 | 0 | 3 | 18 |
| Regex (ungated) | N/A | 0.000 | 0.000 | 0 | 0 | 8 | 18 |
| Regex (source topic gated) | N/A | 0.000 | 0.000 | 0 | 0 | 8 | 18 |

## Polarity by practice type

| Practice | Positive pair support | Micro F1 | Supported-label macro F1 |
| --- | ---: | ---: | ---: |
| sale | 14 | 0.609 | 0.465 |
| business_transfer | 7 | 0.923 | 0.923 |
| aggregate_sale | 0 | N/A | N/A |
| recipient_onward_sale | 1 | 1.000 | 1.000 |
| data_broker_relationship | 0 | N/A | N/A |

## Limits

- This is a small, keyword-selected test cohort; results measure agreement with the supplied annotations, not general privacy-risk accuracy.
- Per-label confusion matrices use [[TN, FP], [FN, TP]]. Labels with zero support have null recall; supported-label macro F1 excludes them.
- Predictions describe paragraph-level labels, not extracted evidence spans or resolved scopes.
- 1 test paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a training paragraph.
- Keep these results as a final measurement of this saved model. Any subsequent model changes need a separate evaluation protocol.

See test_predictions.jsonl for individual errors and margins, test_metrics.json for full metrics, and evaluation.json for input/model hashes.
