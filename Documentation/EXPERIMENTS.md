# Reproducible classifier and Stage 1 demo

Run commands from the repository root. Install `requirements.txt` in a virtual environment. The recorded SVM run uses Python 3.10.11; `requirements.txt` pins the versions used here. Encoder downloads use Hugging Face. GPU training is recommended for the encoder sequence.

## Evaluation contract and frozen data

`data/versions/v1/manifest.json` identifies the benchmark by SHA-256, preserves company/policy splits, and records label order and mapping hashes. All 66 rows belonging to the 28 normalized texts appearing across splits are quarantined, from every affected split. This avoids choosing a retained copy using its label or favoring any split. Within-split duplicates are retained. The original processed data is unchanged.

The frozen classifier contains 25,893 rows: 3,663 OPP-115 and 22,230 C3PA rows. Extraction rows are filtered to the same retained OPP-115 IDs. `quarantine.jsonl` allows inspection of every removed row. V1 is immutable: the freeze command refuses to overwrite it. Future changes require a new version and fresh experiment runs.

OPP-115 supplies fully labelled precision/recall/F1. C3PA supervises positives only; unknown labels remain masked. C3PA scores report positive-label recall, never F1 or precision. An always-positive classifier gets perfect positive recall and must not be selected on this metric. Model and threshold selection use validation only. Test metrics are final measurements for the already frozen configuration; do not use test outcomes to choose another configuration.

`configs/label_schema.json` owns label order. `configs/label_mapping.json` owns the five-category C3PA mapping and dropped original labels. Preprocessing and integration load these files. PolicyIE is planned and has no integrated data yet.

## SVM baseline

```sh
python3 -m scripts.train_baseline --seed 42 --out runs/svm-opp115-seed42
python3 -m scripts.evaluate_test --run runs/svm-opp115-seed42
python3 -m demo.server --run runs/svm-opp115-seed42
```

The one-epoch DistilBERT pilot completed on CPU in 244.7 seconds, with validation macro-F1 0.7182 and micro-F1 0.7626 after threshold tuning. Its CPU scoring averaged 15.2 ms/segment and its saved artifacts occupy approximately 269 MB. SVM remains the demo model based on validation. Encoder test data has not been evaluated.

The saved run already exists, so the training command refuses to overwrite it. Use another directory for reproduction. TF-IDF is fitted on training text only, with unigrams/bigrams, 50,000 maximum features, and minimum document frequency 2. One-vs-rest LinearSVC uses balanced class weights and C=1. Per-category thresholds maximize validation F1 over decision margins [-3, 3] in 0.05 increments, with conservative tie-breaking. These are decision margins, not calibrated probabilities. The fitted TF-IDF vocabulary/tokenization is stored inside `model.joblib`; encoder runs additionally save a Hugging Face tokenizer.

The run contains model, label order, thresholds, validation and test metrics with positive/negative supports, dataset hashes, software versions, wall-clock training time, artifact size, and CPU inference latency. Timing includes vectorization and classification, averaged over validation segments; it is not an end-to-end web latency SLA.

## Encoder sequence

```sh
HF_HOME=.model-cache python3 -m scripts.train_encoder --model distilbert-base-uncased --source opp115 --seed 42 --out runs/distilbert-opp115-seed42
HF_HOME=.model-cache python3 -m scripts.train_encoder --model roberta-base --lr 2e-5 --source opp115 --seed 42 --out runs/roberta-opp115-seed42
```

Start with seed 42. Record selection with `python3 -m scripts.select_run --runs <candidate-run-directories> --out selection.json`, which reads validation metrics only. Select the candidate using validation metrics, then repeat shortlisted configurations with seeds 13 and 7. Compare accuracy, CPU latency, artifact size, and peak training memory. For supplementation, reuse the selected model and settings, changing only source and C3PA weight:

```sh
HF_HOME=.model-cache python3 -m scripts.train_encoder --model distilbert-base-uncased --source combined --c3pa-weight 0.1 --out runs/distilbert-combined-weight01
HF_HOME=.model-cache python3 -m scripts.train_encoder --model distilbert-base-uncased --source combined --c3pa-weight 1.0 --out runs/distilbert-combined-weight10
```

The custom masked BCE loss uses `label_mask` and saved row weights. A multiplier controls C3PA's contribution. Positive-class weights multiply only the positive BCE term; they are computed from supervised train labels and clipped to [1,10]. Unknown entries have zero gradient. Long segments are windowed at 512 tokens with stride 128; each window receives a fraction of its original row weight. Inference takes maximum logits over windows. AdamW, 10% warmup, linear decay, and early stopping after two unimproved validation epochs are implemented. Epoch selection uses validation F1 at probability 0.5; thresholds are tuned after restoring the selected checkpoint. A one-epoch pilot is a pipeline check, not a full encoder comparison. Domain adaptation should follow reliable supervised comparisons; it is not implemented in this milestone.

## Fully reviewed modern validation/test data

`data/versions/v1/modern_review_template.jsonl` contains 948 retained segments from ten modern company groups per split. Reviewers must explicitly label every category true or false and record a distinct reviewer and adjudicator. Null judgments cannot become negatives automatically. Existing training annotations are deliberately hidden from the review template.

```sh
python3 -m scripts.modern_review --reviewed completed_reviews.jsonl --out data/versions/v1/modern_reviewed.jsonl
python3 -m scripts.evaluate_modern --run runs/svm-opp115-seed42 --reviewed data/versions/v1/modern_reviewed.jsonl --split validation
```

Select configurations and, if warranted, tune thresholds using reviewed validation only, before opening reviewed test judgments. `evaluate_modern` measures the currently saved thresholds; it does not retune them. Reviews cover retained annotated C3PA segments, not all text in each original policy. Full-policy silence evaluation requires reviewing complete policies including previously unannotated text. Human review remains outstanding; the template is not a gold dataset.

## Demo acceptance

Open http://127.0.0.1:8765. Paste a policy with blank lines between paragraphs, classify, and click any evidence clause. The original submitted text is preserved; every displayed clause is an exact substring identified by character offsets. FAQ cards and all ten categories use complete classified segments. Unmatched categories say “No matching clause detected.” Policy HTML is displayed as text, never executed. User submissions are not written to disk. URL ingestion and attribute span highlighting are deferred.

```sh
python3 -m unittest discover -s tests -v
```

The meaningful contract checks cover rejected positive-only F1, zero unknown-label gradients, row and positive weights, source offsets, and company/text split isolation. Browser acceptance checks cover submit → results → selected source highlighting.
