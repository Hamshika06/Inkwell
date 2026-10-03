## Model Documentation


# Overview

- Inkwell's core model is a **multi-label clause classifier**: it reads one privacy-policy segment and outputs a probability for each category in the unified label schema.
- We fine-tune two encoders, **DistilBERT** and **RoBERTa-base**, on the combined OPP-115 + C3PA training set, and select using validation metrics; evaluate the selected configuration once on test. Full modern F1 awaits human-reviewed labels.
- This single model powers every downstream feature:
  - **FAQ answers** (Stage 1)
  - **Silence detection** (Stage 1)
  - **Category rerank in open Q&A** (Stage 2)
- The span extractor and retrieval components are documented separately.

| Field | Value |
| --- | --- |
| Task | Multi-label text classification (segment → set of categories) |
| Input | One policy segment (paragraph), max 512 subword tokens |
| Output | One sigmoid probability per category + thresholded label set |
| Candidate backbones | `distilbert-base-uncased` (66M params), `roberta-base` (125M params) |
| Training data | OPP-115 (115 policies, 2016) + C3PA (411 policies, 2024), merged via `configs/label_mapping.json` |
| Label schema | OPP-115's 10 categories (C3PA's 5 mapped categories mapped onto them) |
| Primary metric | Macro-F1 on fully labelled OPP-115 validation; modern F1 pending reviewed data |
| Generative components | None. No LLM API, no generated text. |
| Owner | Engineering (training), Data and Evaluation (metrics) |
| Status | In development, Fall 2026 |

> **Note:** "Combined datasets" = OPP-115 + C3PA. PolicyIE is used as a Retention/Security supplement and for domain-adaptive pretraining.

---

## The two models

- We compare a **small, fast** encoder against a **larger, more robust** one, so the choice between them is measured rather than assumed.
- **DistilBERT** is the latency and cost baseline.
- **RoBERTa-base** is the accuracy candidate.

| Attribute | DistilBERT | RoBERTa-base |
| --- | --- | --- |
| Hugging Face ID | `distilbert-base-uncased` | `roberta-base` |
| Parameters | ~66M | ~125M |
| Layers / hidden / heads | 6 / 768 / 12 | 12 / 768 / 12 |
| Tokenizer | WordPiece, 30,522 vocab, lowercased | Byte-level BPE, 50,265 vocab, cased |
| Max sequence length | 512 | 512 |
| Pretraining | Distilled from BERT-base (BooksCorpus + Wikipedia) | 160GB text incl. web crawl (CC-News, OpenWebText) |
| Relative inference speed | ~2x faster than RoBERTa-base | Baseline |
| License | Apache 2.0 | MIT |

### Why DistilBERT

- **Cheap to serve:** the README commits to local compute only. Half the layers means roughly half the CPU latency per segment, and a policy has 50–150 segments.
- **Fast iteration:** shorter training runs let us sweep thresholds, loss weights and learning rates within course deadlines.
- **Honest floor:** if DistilBERT matches RoBERTa on modern policies, we ship the cheaper model.

### Why RoBERTa-base

- **Stronger text understanding:** longer training, more data and dynamic masking typically give better classification results.
- **Web-text pretraining:** its corpus includes web pages, closer to how policies are written than DistilBERT's books and Wikipedia.
- **Cased BPE tokenizer:** keeps signals like `GDPR`, `CCPA` and `California` intact rather than lowercasing them or splitting them into many pieces.
- **Same family as PrivBERT:** domain-adaptive pretraining and a PrivBERT comparison reuse the exact same code.

### Trade-offs we expect to observe

- RoBERTa should win on **rare categories** (Data Retention, Data Security, Policy Change), where nuance matters.
- DistilBERT may be within **1–3 macro-F1 points** on frequent categories (First Party, Third Party).
- Both are limited to **512 tokens**, so long segments are handled with a sliding window (stride 128, max of window probabilities).

---

## Architecture and training setup

- Both backbones use the **same head, loss and schedule**; only the model ID and learning rate change.
- This keeps the DistilBERT vs. RoBERTa comparison fair.

### Architecture

- Pipeline: segment text → tokenizer → encoder → pooled `[CLS]` / `<s>` vector (768-d) → dropout (0.1) → linear layer (768 → 10) → sigmoid per category.
- Hugging Face implementation: `AutoModelForSequenceClassification` with `num_labels=10`, plus a custom training loop that consumes masks and row weights; built-in multi-label loss alone does not implement this contract.

### Loss

- **Masked, class-weighted binary cross-entropy.** For segment *i* and category *c*, with mask *m*, row weight *w*, positive-class weight *p_c*, and logit *z*:

$$
L = \frac{\sum_{i,c} w_i m_{ic} [-p_c y_{ic}\log \sigma(z_{ic})-(1-y_{ic})\log(1-\sigma(z_{ic}))]}{\sum_{i,c}w_i m_{ic}}
$$

- **Mask (m):** combined C3PA rows supervise their positive labels only. All other entries are unknown and excluded from loss.
- **Positive-class weight (p_c):** supervised negatives / positives from training, clipped to [1, 10]. It multiplies only the positive term. Row weights multiply the entire masked loss. See `inkwell/loss.py` for the implemented formula.
- **Focal loss** (gamma = 2) is an ablation, not the default.

### Hyperparameters

| Setting | DistilBERT | RoBERTa-base |
| --- | --- | --- |
| Learning rate (sweep) | 5e-5 {3e-5, 5e-5} | 2e-5 {1e-5, 2e-5, 3e-5} |
| Batch size | 16 | 16 (grad accumulation 2 if memory-bound) |
| Epochs | Up to 10, early stop patience 2 on val macro-F1 | Same |
| Optimizer | AdamW, weight decay 0.01 | Same |
| Scheduler | Linear decay, 10% warmup | Same |
| Max length | 512 | 512 |
| Precision | fp16 on GPU | fp16 on GPU |
| Seeds | 3 (42, 13, 7); report mean ± std | Same |

### Decision thresholds

- A fixed **0.5 threshold under-predicts rare categories**.
- After training, pick **one threshold per category** that maximizes F1 on the validation set:
  - Scan 0.05–0.95 in steps of 0.05.
  - Use only validation rows where the mask is 1.
  - Save to `models/<run>/thresholds.json`.
- **Silence detection uses these same thresholds:** a category is "not addressed" only when no segment in the policy crosses its tuned threshold.

### Optional: domain-adaptive pretraining

- Before fine-tuning, continue masked-language-model training for **1–2 epochs** on raw C3PA + PolicyIE text (15% masking, lr 5e-5).
- This produces the "domain-adapted" rows in the evaluation table.

### Compute

- Both models train on a **single free-tier GPU** (Colab T4, 16GB).
- Record **wall-clock time per epoch** and **CPU inference latency per segment** for each; these feed the Cost to serve section of the README.

---

## Evaluation

- **Selection metric: macro-F1 on OPP-115 validation.** C3PA currently supports positive-label recall only, not precision or F1. A fully reviewed modern benchmark is required before modern F1 can guide selection.
  - It weights rare categories equally.
  - It measures the policies real users will paste in today.
- Full precision/recall/F1 requires explicit positives and negatives for every category. Positive-only C3PA masks are used for training and positive-label recall checks only. Tune thresholds and select models on validation; evaluate the frozen configuration once on test.

### Metrics

| Metric | What it answers | Why we report it |
| --- | --- | --- |
| Per-category precision, recall, F1 | How good is each category? | Rare categories (Retention, Security) drive FAQ and silence quality |
| Macro-F1 (primary) | Average quality across categories | Not dominated by First Party / Third Party |
| Micro-F1 | Overall hit rate across all labels | Comparable to published OPP-115 work |
| Weighted-F1 | Quality weighted by frequency | Reflects what users see most often |
| Subset accuracy (exact match) | Did we get the whole label set right? | Strict sanity check for multi-label |
| Hamming loss | Fraction of individual labels wrong | Complements exact match |
| ROC-AUC / PR-AUC per category | Ranking quality, threshold-free | Shows whether tuned thresholds are the bottleneck |
| Expected calibration error | Are probabilities trustworthy? | Silence detection relies on confidence |
| Silence detection precision / recall | Are "not addressed" flags correct? | A false "not addressed" is the most harmful error |
| Latency (ms/segment, CPU) and model size (MB) | Can we serve it cheaply? | README cost-to-serve commitment |

### Experiments

| # | Experiment | Compares | Test sets |
| --- | --- | --- | --- |
| E1 | Baselines | TF-IDF + linear SVM; regex matcher | Old, modern |
| E2 | Backbone head-to-head | DistilBERT vs. RoBERTa-base, OPP-115 only | Old, modern |
| E3 | Data combination | OPP-115 only vs. OPP-115 + C3PA | Old, modern |
| E4 | Domain adaptation | E3 winner with vs. without MLM pretraining | Old, modern |
| E5 | Ablations | Loss mask on/off; class weights on/off; 0.5 vs. tuned thresholds | Modern |
| E6 (stretch) | Domain-pretrained backbone | PrivBERT fine-tuned the same way | Old, modern |

- **Significance:** 3 seeds per configuration, plus a paired bootstrap (1,000 resamples over policies) on macro-F1 for the final pairwise comparison.

### Implemented milestone

The SVM baseline and Stage 1 demo are runnable; the masked encoder trainer is implemented. Follow [experiment instructions](../EXPERIMENTS.md). Frozen OPP-115 v1 baseline test scores are macro-F1 0.7004 and micro-F1 0.7459. Modern full F1 awaits human-reviewed labels. The architecture and experiment matrix below describe the target system, not completed encoder experiments.

### Results (encoder comparison pending)

| Model | Train data | Macro-F1 old | Macro-F1 modern | Micro-F1 modern | Latency (ms/seg) |
| --- | --- | --- | --- | --- | --- |
| TF-IDF + SVM | OPP-115 + C3PA | TBD | TBD | TBD | TBD |
| DistilBERT | OPP-115 | TBD | TBD | TBD | TBD |
| RoBERTa-base | OPP-115 | TBD | TBD | TBD | TBD |
| DistilBERT | OPP-115 + C3PA | TBD | TBD | TBD | TBD |
| RoBERTa-base | OPP-115 + C3PA | TBD | TBD | TBD | TBD |
| Best + domain-adapted | OPP-115 + C3PA | TBD | TBD | TBD | TBD |

- **Sanity targets (policy-disjoint splits):**
  - SVM baseline near 0.60–0.70 macro-F1 on old text; fine-tuned encoders above it.
  - A policy-disjoint study reported BERT-base at 0.706 macro-F1 on OPP-115, and found random splits inflate scores by up to 0.123 ([source](https://github.com/Sammy6899/leakage-aware-privacy-policy-classification)).
  - A modern score well below the old score confirms the drift the project is designed to measure.

### Error analysis

- For the shipped model, log:
  - A confusion matrix of co-occurring categories.
  - The 20 highest-confidence false positives and false negatives per rare category.
  - Every silence-detection false alarm.
- Write findings to `docs/error_analysis.md`.

---

## User flow and expected output

- The user pastes a policy **once**; the classifier runs over every segment, and all three features read from that one pass.
- The user never sees raw probabilities unless they expand a clause.

### User flow

1. **Submit:** the user pastes policy text or a URL (e.g., a student checking a study app's policy).
2. **Segment:** Inkwell splits the policy into paragraphs and shows a progress bar (target: under 5 s for a 5,000-word policy on CPU).
3. **Classify:** the model tags each segment with zero or more categories using tuned thresholds.
4. **Stage 1, coverage view:** all 10 categories are shown, each marked *Addressed* (with its clause count) or *Not addressed*.
5. **Stage 1, FAQ cards:** fixed questions ("Can I delete my data?", "Do they share it?", "How long do they keep it?") each show the top clauses from the matching category, quoted verbatim with a link to their position in the policy.
6. **Stage 2, ask a question:** the user types a free question; retrieval ranks classified segments, boosting those whose category matches the question.
7. **Verify:** clicking any clause highlights it in the full policy using `char_start` / `char_end`.
8. **Feedback:** a "wrong label" button logs the segment and label (anonymized) for error analysis.

### Expected output: one segment

**Input:**

> "We keep your account information for as long as your account is active and for up to 30 days after you request deletion. You can delete your account at any time from Settings."

**Output:**

```json
{
  "segment_id": "user_policy_s031",
  "labels": ["Data Retention", "User Access, Edit and Deletion"],
  "scores": {
    "First Party Collection/Use": 0.21, "Third Party Sharing/Collection": 0.03,
    "User Choice/Control": 0.18, "User Access, Edit and Deletion": 0.91,
    "Data Retention": 0.94, "Data Security": 0.02, "Policy Change": 0.01,
    "Do Not Track": 0.00, "International and Specific Audiences": 0.01, "Other": 0.04
  },
  "char_start": 8120, "char_end": 8301
}
```

### Expected output: whole policy (Stage 1)

```json
{
  "policy_id": "user_policy",
  "model": "roberta-base-inkwell-v1",
  "num_segments": 64,
  "coverage": {
    "First Party Collection/Use": {"status": "addressed", "clauses": 14},
    "Third Party Sharing/Collection": {"status": "addressed", "clauses": 9},
    "User Access, Edit and Deletion": {"status": "addressed", "clauses": 3},
    "Data Retention": {"status": "addressed", "clauses": 1},
    "Data Security": {"status": "not_addressed", "clauses": 0, "max_score": 0.22},
    "Do Not Track": {"status": "not_addressed", "clauses": 0, "max_score": 0.04}
  },
  "faq": [
    {"question": "Can I delete my data, and how?",
     "category": "User Access, Edit and Deletion",
     "clauses": [{"segment_id": "user_policy_s031", "score": 0.91,
                  "text": "You can delete your account at any time from Settings."}]}
  ]
}
```

- The coverage list above is trimmed; the real output lists all 10 categories.
- `max_score` on a *not addressed* category tells reviewers how close it came to the threshold.

### Expected output: open question (Stage 2)

```json
{
  "question": "Do they sell my data to advertisers?",
  "predicted_category": "Third Party Sharing/Collection",
  "results": [
    {"rank": 1, "segment_id": "user_policy_s018", "category": "Third Party Sharing/Collection",
     "retrieval_score": 0.47,
     "text": "We do not sell your personal information. We share limited data with advertising partners..."}
  ]
}
```

- **No field in any output is generated text:** every `text` value is a substring of the submitted policy.

---

## Limitations, licensing and delivery

- The model classifies **what a policy says**; it cannot judge whether a practice is legal, fair or actually followed.
- Every user-facing screen repeats **"not legal advice."**

### Known limitations

- **Modern gaps:** Do Not Track and International/Specific Audiences have OPP-115 labels only (2016 language); modern recall is unmeasured unless we hand-label a small batch.
- **Retention and Security:** these rely on OPP-115 plus the PolicyIE supplement, so modern scores there have wider error bars.
- **Silence is threshold-dependent:** a "not addressed" flag means no segment crossed a tuned threshold, not proof of absence.
- **512-token limit:** very long segments are windowed; a clause split across windows may be missed.
- **Language:** English only, mostly US-style policies.
- **Boilerplate:** cross-company template text can inflate scores; we report the exact-duplicate rate between train and test.

### Licensing

| Asset | License | Constraint for us |
| --- | --- | --- |
| OPP-115 | Research/teaching (CC BY-NC-style) | Coursework OK; no commercial use |
| C3PA | No stated license on repo | Confirm with authors before any public release |
| DistilBERT | Apache 2.0 | None |
| RoBERTa-base | MIT | None |
| PrivBERT (stretch) | CC BY-NC-SA | Coursework OK; share-alike on derivatives |

- Because of the OPP-115 and C3PA terms, **fine-tuned weights are shared only within the course**, not published to the Hugging Face Hub.

### Ownership

| Hat | Owns in this model |
| --- | --- |
| Engineering (Hamshika) | Training script, inference API, packaging |
| Data and Evaluation (Swetha) | Splits, label mapping, metrics, error analysis |
| Product (Aniruddhan) | FAQ question-to-category map, silence UX |
| Users and Research (Sreya) | Tester judgments of FAQ correctness |
| Operations (Gowtham) | Compute, run tracking, `models/shipped` tag |

### Delivery checklist

- [ ] `configs/label_mapping.json` finalized, C3PA mapping reviewed by two teammates
- [ ] Splits frozen by `policy_id`; duplicate-overlap rate reported
- [ ] Baselines (SVM, regex) scored on old and modern test sets
- [ ] DistilBERT and RoBERTa-base trained with 3 seeds each
- [ ] Per-category thresholds tuned on validation only
- [ ] Results table in README filled from `models/shipped`
- [ ] Error analysis written to `docs/error_analysis.md`
- [ ] Latency and model size measured on CPU