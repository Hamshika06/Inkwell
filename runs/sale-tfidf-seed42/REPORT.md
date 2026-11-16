# TF-IDF practice/polarity baseline

Training: 137 paragraphs. Validation: 18 paragraphs. Seed: 42.

The vectorizer and models were fitted on training text only. Word unigrams/bigrams and balanced binary LinearSVC classifiers predict paragraph-level practice/polarity pairs. Thresholds are fixed at zero; there was no validation tuning or test evaluation.

## Validation results

| Task | Micro F1 | Macro F1 (supported labels) | Exact match |
| --- | ---: | ---: | ---: |
| joint | 0.897 | 0.786 | 0.889 |
| practice_type | 0.929 | 0.964 | 0.889 |

## Sale flag comparison

A sale flag means permitted or conditional first-party personal-information sale. Contextual practices and denied/unclear statements are negative for this target.

| Method | Precision | Recall | F1 | TP | FP | FN | TN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TF-IDF | 1.000 | 0.600 | 0.750 | 3 | 0 | 2 | 13 |
| Regex (ungated) | N/A | 0.000 | 0.000 | 0 | 0 | 5 | 13 |
| Regex (source topic gated) | N/A | 0.000 | 0.000 | 0 | 0 | 5 | 13 |

## Polarity by practice type

| Practice | Positive pair support | Micro F1 | Macro F1 (supported labels) |
| --- | ---: | ---: | ---: |
| sale | 9 | 0.800 | 0.571 |
| business_transfer | 5 | 1.000 | 1.000 |
| aggregate_sale | 1 | 1.000 | 1.000 |
| recipient_onward_sale | 1 | 1.000 | 1.000 |
| data_broker_relationship | 0 | N/A | N/A |

## Interpretation

1 validation paragraphs have train-fitted TF-IDF cosine similarity >= 0.90 to a training paragraph. Below that threshold, 17 paragraphs have joint micro F1 0.889.

Each label's confusion matrix in validation_metrics.json is [[TN, FP], [FN, TP]]. Recall is null when its reference support is zero. Macro F1 averages only labels with positive validation support; micro F1 also counts false predictions for unsupported labels.

- Small keyword-selected candidate dataset; scores are not representative of all privacy clauses.
- Reference annotations include AI-authored drafts; metrics measure agreement with these annotations.
- No validation unclear examples; unsupported-label recall is undefined.
- Model does not extract scoped propositions, conditions, exceptions or evidence spans; repeated identical pairs collapse to one label.
- Pairs absent from training always predict negative; their -1 score is a constant sentinel, not a learned margin.
- SVM margins are not calibrated probabilities; no deployment or risk-score integration is performed.

Inspect validation_predictions.jsonl for every prediction, raw decision margin and nearest training template. No matching prediction is not a safety judgment.
