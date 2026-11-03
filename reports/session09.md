---
team: Token Economy
session: Session 9
date: 11/03/2026
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

_Week of November 2, 2026. The items below were merged to `main` today._

- **Email confirmation for sign-up.** PR [#52](https://github.com/Hamshika06/Inkwell/pull/52) fixes last week's account-flow problem. New email and password accounts now see a "Check your inbox" screen and cannot analyze policies until they confirm their address; the API returns 403 until they do. The screen offers "Resend email" (with a 60-second cooldown) and "Use a different email". Google and GitHub sign-ins skip the check. Three new API tests cover verified, unverified, and invalid-token cases, and `DEPLOYMENT.md` and `api/README.md` document the new behaviour.
- **Sale-practice annotation batch for risk scoring.** PR [#51](https://github.com/Hamshika06/Inkwell/pull/51) recovers the original OPP-115 attributes (Does/Does Not, Action Third Party, Choice Type and Scope) and searches the 3,663 retained segments for sale-related wording. This produced 182 candidate segments from 100 policies, kept in the existing frozen splits (137 train, 18 validation, 27 test). A draft annotation of all 137 training candidates records 123 practice entries, each with a polarity label: 72 conditional, 34 denied, 11 permitted, and 6 unclear. The draft is AI-generated and has not been reviewed, so it is not ground truth yet. The PR also adds `scripts/sale_review.py` to export and validate batches, with tests, and a progress write-up in [`RISK_SCORING_PROGRESS.md`](../Documentation/RISK_SCORING_PROGRESS.md).
- **GoPPC preprocessing.** PR [#55](https://github.com/Hamshika06/Inkwell/pull/55) adds the GoPPC training CSV, a preprocessing script, and a mapping from GoPPC taxonomy IDs to five broad classes (Data Collection & Use, Data Sharing, User Rights & Choices, Data Security & Retention, Policy Scope & Changes). This is a separate five-class task; it does not change Inkwell's ten-category schema. Of 6,485 input rows, 6,250 were kept after removing 74 blank rows and 161 exact duplicates. The file is a training split only, and its rows have no policy IDs, so it cannot yet be used for validation, testing, or policy-level splits.
- **PolicyIE in the shared classifier format.** PR [#58](https://github.com/Hamshika06/Inkwell/pull/58) updates the PolicyIE preprocessing so its 690 paragraphs are written in the same row format as the frozen classifier data. Each row now carries its split, a label vector over the shared categories, a label mask, and a training weight. PolicyIE releases adjudicated labels only, so per-annotator fractions and annotator counts are left empty. This makes PolicyIE ready to be combined with the other datasets.
- **DistilBERT combined-data test result and README updates.** PR [#57](https://github.com/Hamshika06/Inkwell/pull/57) adds the held-out test metrics for the DistilBERT model trained on OPP-115 + C3PA (dataset v2): 0.694 macro-F1 and 0.757 micro-F1, slightly below DistilBERT trained on OPP-115 only (0.703 / 0.769). Its Data Retention F1 on test is 0.0. The README now links to the [live web app](https://inkwell-846713605562.us-east1.run.app/), lists the three models the app serves, and drops the unused regex baseline row from the evaluation table.

## User evidence

No new user-testing session was recorded this week. This week's account-flow change addresses the Week 7 report that the product appeared to create an account from invalid credentials ([issue #42](https://github.com/Hamshika06/Inkwell/issues/42)). Firebase still creates the account before the address is confirmed, but an unconfirmed account can no longer use the app.

## New week's Goal

- **Combine OPP-115, PolicyIE and GoPPC into one five-class dataset.** Map each dataset's labels to the five broad classes already used for GoPPC: Data Collection & Use, Data Sharing, User Rights & Choices, Data Security & Retention, and Policy Scope & Changes. Remove duplicate text across the sources, keep each source's existing train/validation/test splits, and record the mapping and row counts in a data manifest.
- **Mitigate class imbalance.** Measure how many examples each of the five classes has in the combined dataset. Then try class weighting or resampling on the training split only, so smaller classes are not drowned out. Last week's test results show why this matters: Data Retention, one of the smallest categories, scored 0.0 F1 for the DistilBERT combined-data model.
- **Fine-tune RoBERTa on the combined dataset.** RoBERTa-base has the best OPP-115 test results so far (0.740 macro-F1 and 0.800 micro-F1), so it will be the model trained on the new five-class data. Select thresholds on validation and evaluate on the held-out test set once.
- **Continue the risk score features.** Review the drafted sale-practice annotations, finalize the annotation guidelines, and annotate the validation data with the same guidelines, keeping the test split sealed. Then train a first practice and polarity detector and compare it against the current rule-based risk engine.
- **Turn the web app into a browser extension.** Build an extension that can send the privacy policy on the current page to the existing API and show the classified clauses and risk score without leaving the page.

## Individual Contributions

1. Aniruddhan: Added email confirmation to sign-up and the API's 403 check in PR [#52](https://github.com/Hamshika06/Inkwell/pull/52).
2. Swetha: Converted the PolicyIE rows to the shared classifier format in PR [#58](https://github.com/Hamshika06/Inkwell/pull/58).
3. Hamshika: Added the DistilBERT v2 test metrics and updated the README in PR [#57](https://github.com/Hamshika06/Inkwell/pull/57), and drafted this weekly report.
4. Gowtham S: Built the sale-practice candidate batch, annotation draft, and review tooling in PR [#51](https://github.com/Hamshika06/Inkwell/pull/51).
5. Sreya: Added GoPPC preprocessing and its class mapping in PR [#55](https://github.com/Hamshika06/Inkwell/pull/55).
