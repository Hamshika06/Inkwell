---
team: Token Economy
session: Session 5
date: 9/29/2026
members:
  - name: Hamshika Radhakrishnan
    github: Hamshika06
    hat: Engineering
  - name: Swetha Rathinavelu Saravanakumar
    github: swecodes
    hat: Data&Eval
  - name: Sreya Nagulapati
    github: sreya-design
    hat: User & Research
  - name: Aniruddhan Narasimhan
    github: aniruddhan
    hat: Product
  - name: Gowtham S
    github: gowthamsenthil
    hat: Operations
north_star:
  metric: Number of privacy policies correctly classified
  value: 0
  previous: 0
---

## Shipped this week
 
_Week of September 28, 2026. Everything below is merged to `main`. Nothing is deployed yet._
 
- **C3PA dataset pipeline.** Adds an EDA script, a preprocessing script, and the shared 10-category label schema ([`configs/label_schema.json`](../configs/label_schema.json)). The processed dataset has 22,409 units from 398 policies, cut down from 29,260 raw units by vote, label mapping, a length filter, and deduplication. (evidence: [PR #7](https://github.com/Hamshika06/Inkwell/pull/7))
- **OPP-115 EDA.** [`eda/opp115_eda.py`](../eda/opp115_eda.py) produces 10 figures (category counts, co-occurrence, annotator agreement, sector breakdowns), 13 tables, and a summary report. (evidence: [PR #10](https://github.com/Hamshika06/Inkwell/pull/10))
- **OPP-115 preprocessing.** [`preprocessing/opp115_preprocess.py`](../preprocessing/opp115_preprocess.py) builds three interim datasets (general, classifier, extraction) with 3,729 segments from 115 policies. The 63 segments with no majority label are dropped. It also writes a decision log, a span report, and a threshold comparison. (evidence: [PR #14](https://github.com/Hamshika06/Inkwell/pull/14))
- **Model design doc.** [`Documentation/Models/Model.md`](../Documentation/Models/Model.md) compares DistilBERT and RoBERTa-base. It covers the training setup, the evaluation plan, the user flow with expected outputs, and licensing. The results section is still pending. (evidence: [PR #13](https://github.com/Hamshika06/Inkwell/pull/13))
- **README rewrite.** Adds sections on the problem and user, how Inkwell works, data and licensing, models, evaluation, limitations, ethics, and cost to serve. (evidence: [PR #11](https://github.com/Hamshika06/Inkwell/pull/11))


## New week's Goal
 
- **Combined OPP-115 + C3PA training data.** [`data_integration/combine_opp115_c3pa.py`](../data_integration/combine_opp115_c3pa.py) merges the two sources into `data/processed/combined_classifier.jsonl` (25,959 rows) and `combined_extraction.jsonl` (3,729 OPP-115 rows with span tags). It removes 179 C3PA units that duplicate OPP-115 text and keeps OPP-115's original splits. C3PA is split by company so no company appears in more than one split. C3PA rows are masked so they only supervise their positive labels. All integrity checks pass, with one inherited warning: 28 texts repeat across splits inside OPP-115 itself. (evidence: [PR #15](https://github.com/Hamshika06/Inkwell/pull/15), open, not yet merged)

- Fine tune the model
- Prepare for the mid semester presentation


## Individual Contributions
 
1. Swetha: Built the C3PA EDA and preprocessing scripts, the shared label schema, and the processed C3PA dataset ([PR #7](https://github.com/Hamshika06/Inkwell/pull/7)).
2. Hamshika: Built the OPP-115 EDA script and outputs ([PR #10](https://github.com/Hamshika06/Inkwell/pull/10)) and the OPP-115 preprocessing script, interim datasets, and reports ([PR #14](https://github.com/Hamshika06/Inkwell/pull/14)), and opened the combined OPP-115 + C3PA dataset with its combine script and reports ([PR #15](https://github.com/Hamshika06/Inkwell/pull/15)).
3. Aniruddhan: Wrote the model documentation covering model choice, training setup, evaluation plan, and user flow ([PR #13](https://github.com/Hamshika06/Inkwell/pull/13)).
4. Sreya: Rewrote the README with the problem, user, pipeline, data, evaluation, limitations, and ethics sections ([PR #11](https://github.com/Hamshika06/Inkwell/pull/11)).
5. Gowtham S: Reviewed and merged PRs [#10](https://github.com/Hamshika06/Inkwell/pull/10), [#14](https://github.com/Hamshika06/Inkwell/pull/14) and [#15](https://github.com/Hamshika06/Inkwell/pull/15), and compiled this weekly report.