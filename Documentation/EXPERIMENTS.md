# Reproducible classifier and Stage 1 demo

Run commands from the repository root. Install `requirements.txt` in a virtual environment. The recorded SVM run uses Python 3.10.11; `requirements.txt` pins the versions used here.

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

The one-epoch DistilBERT pilot completed on CPU in 244.7 seconds, with validation macro-F1 0.7182 and micro-F1 0.7626 after threshold tuning. Its CPU scoring averaged 15.2 ms/segment and its saved artifacts occupy approximately 269 MB. SVM remains the demo model based on validation. The full multi-epoch fine-tune in the next section replaces the pilot as the DistilBERT result.

The saved run already exists, so the training command refuses to overwrite it. Use another directory for reproduction. TF-IDF is fitted on training text only, with unigrams/bigrams, 50,000 maximum features, and minimum document frequency 2. One-vs-rest LinearSVC uses balanced class weights and C=1. Per-category thresholds maximize validation F1 over decision margins [-3, 3] in 0.05 increments, with conservative tie-breaking. These are decision margins, not calibrated probabilities. The fitted TF-IDF vocabulary/tokenization is stored inside `model.joblib`; encoder runs additionally save a Hugging Face tokenizer.

The run contains model, label order, thresholds, validation and test metrics with positive/negative supports, dataset hashes, software versions, wall-clock training time, artifact size, and CPU inference latency. Timing includes vectorization and classification, averaged over validation segments; it is not an end-to-end web latency SLA.

## DistilBERT fine-tune (OPP-115 only)

```sh
python -m scripts.train_encoder --model distilbert-base-uncased --source opp115 --epochs 20 --batch-size 16 --lr 5e-5 --seed 42 --out runs/distilbert-opp115-seed42
python -m scripts.train_encoder --model distilbert-base-uncased --source opp115 --epochs 20 --batch-size 16 --lr 5e-5 --seed 13 --out runs/distilbert-opp115-seed13
python -m scripts.train_encoder --model distilbert-base-uncased --source opp115 --epochs 20 --batch-size 16 --lr 5e-5 --seed 7 --out runs/distilbert-opp115-seed7
python -m scripts.evaluate_test --run runs/distilbert-opp115-seed42
```

`distilbert-base-uncased` is fine-tuned on OPP-115 training rows only (`--source opp115`; C3PA is not used). Training runs for up to 20 epochs and stops early after 2 epochs without improvement in validation macro-F1. Batch size is 16 and the learning rate is 5e-5. Thresholds are tuned on validation. Runs used a Colab GPU (torch 2.11.0+cu130) on frozen dataset v1. Only the small result files are committed; the model and tokenizer folders (about 269 MB per run) are git-ignored.

| Seed | Epochs run | Training time | Validation macro-F1 | Validation micro-F1 |
| --- | --- | --- | --- | --- |
| 42 | 6 | 366 s | 0.8212 | 0.8098 |
| 13 | 11 | 633 s | 0.8405 | 0.8127 |
| 7 | 7 | 427 s | 0.8438 | 0.8187 |
| **Mean ± std** | | | **0.835 ± 0.012** | **0.814 ± 0.005** |

Seed 42 was evaluated once on the OPP-115 v1 test set after the configuration was fixed: **macro-F1 0.7033, micro-F1 0.7694**. Only seed 42 has a test result.

Per-category F1. Validation is the mean ± std over the three seeds; test is seed 42 only; the SVM column is the saved SVM run on test.

| Category | Validation F1 | Val. positives | Test F1 | Test positives | SVM test F1 |
| --- | --- | --- | --- | --- | --- |
| First Party Collection/Use | 0.839 ± 0.006 | 162 | 0.838 | 98 | 0.802 |
| Third Party Sharing/Collection | 0.857 ± 0.008 | 131 | 0.859 | 84 | 0.793 |
| User Choice/Control | 0.692 ± 0.015 | 39 | 0.596 | 37 | 0.658 |
| Data Security | 0.796 ± 0.014 | 17 | 0.788 | 19 | 0.727 |
| International and Specific Audiences | 0.904 ± 0.024 | 30 | 0.759 | 46 | 0.786 |
| User Access, Edit and Deletion | 0.772 ± 0.032 | 18 | 0.703 | 17 | 0.737 |
| Policy Change | 0.984 ± 0.027 | 10 | 0.750 | 15 | 0.636 |
| Data Retention | 0.785 ± 0.112 | 5 | 0.200 | 13 | 0.375 |
| Do Not Track | 1.000 ± 0.000 | 4 | 0.800 | 3 | 0.800 |
| Other | 0.723 ± 0.016 | 114 | 0.741 | 86 | 0.690 |

C3PA positive-label recall for the seed-42 run (recall only; false positives are unmeasured, so this is never used for selection): First Party 0.885, Third Party 0.612, User Choice 0.455, Access/Edit/Deletion 0.492, Policy Change 0.646. The SVM scores 0.890, 0.659, 0.725, 0.500 and 0.636 on the same categories.

### Reading these results

- **DistilBERT and the SVM are about even.** Validation macro-F1 is 0.835 (DistilBERT mean) against 0.832 (SVM, one run). Test macro-F1 is 0.7033 against 0.7004, and test micro-F1 is 0.7694 against 0.7459. The gaps are smaller than the seed-to-seed spread (std 0.012), and the SVM was run once, so neither model can be called better yet.
- **Rare categories are noisy.** Data Retention has 5 validation and 13 test examples, and Do Not Track has 4 and 3. The Data Retention validation score (0.785 ± 0.112) is much higher than its test score (0.20), so the validation figure overstates it.
- **GPU runs are not exactly repeatable.** Additional reruns of seed 42 (not committed) reached validation macro-F1 0.8365 and 0.8432, against 0.8212 for the recorded run. Differences smaller than about 0.02 should not be read as real.
- **Cost:** the saved model is about 269 MB, and CPU scoring took 109 to 126 ms per segment on Colab's CPU. This is a different machine from the pilot's 15.2 ms, so the two are not comparable.
- The demo still uses the SVM. The selection files in `runs/` have not been regenerated with these runs.

## Demo acceptance

Open http://127.0.0.1:8765. Paste a policy with blank lines between paragraphs, classify, and click any evidence clause. The original submitted text is preserved; every displayed clause is an exact substring identified by character offsets. FAQ cards and all ten categories use complete classified segments. Unmatched categories say “No matching clause detected.” Policy HTML is displayed as text, never executed. User submissions are not written to disk. URL ingestion and attribute span highlighting are deferred.

```sh
python3 -m unittest discover -s tests -v
```

The meaningful contract checks cover rejected positive-only F1, zero unknown-label gradients, row and positive weights, source offsets, and company/text split isolation. Browser acceptance checks cover submit → results → selected source highlighting.
