---
team: Token Economy
session: Session 10
date: 11/10/2026
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
  metric: Number of privacy policies correctly classified, risk score
  value: 0
  previous: 0
---

## Shipped this week

_Week of November 9, 2026. Everything below is merged to `main`._

- **One five-class dataset from OPP-115, PolicyIE and GoPPC.** PR [#61](https://github.com/Hamshika06/Inkwell/pull/61) maps all three sources to the five broad classes (Data Collection & Use, Data Sharing, User Rights & Choices, Data Security & Retention, Policy Scope & Changes) and combines them into 10,417 rows: 7,379 train, 1,307 validation and 1,731 test (OPP-115 3,440, PolicyIE 777, GoPPC 6,200). OPP-115 keeps its original splits, every policy sits in one split, near-copies across splits are removed, and classes a source does not label are masked. PolicyIE and GoPPC get validation splits made from whole training policies. The combine report suggests class weights from 1.40 to 9.24 to offset imbalance.
- **RoBERTa fine-tuned on the five-class data.** PR [#62](https://github.com/Hamshika06/Inkwell/pull/62) trains RoBERTa with 3 seeds (42, 13, 7), choosing the epoch and per-class cutoffs on validation only. Test macro-F1 is 0.794–0.798 and micro-F1 0.803–0.804 across seeds. For seed 42, test macro-F1 by source is OPP-115 0.755, PolicyIE 0.812 and GoPPC 0.810. These scores are not comparable with the earlier ten-category results (0.740 macro-F1), because five broad classes is an easier task.
- **Inkwell 1.1.** PR [#63](https://github.com/Hamshika06/Inkwell/pull/63) rebuilds the app around a report card of eight checks (sells your data, targeted ads, sharing, location, retention, deletion, opt-out, policy changes). Each check gives a verdict that tells "they do" from "they say they don't", one line on what it means for the user, and the exact sentence behind it. The checks are wording-based; the model does not decide them. It also adds:
  - a decision bar with the user's priorities and three choices (take the steps, agree, not for me)
  - a "Your steps" checklist with opt-out links and pre-written emails
  - "My policies", which saves a check and shows what changed when the policy is checked again
  - a new home page, and a free check for visitors without an account (up to 300 KB)

  The app now serves only the five-class RoBERTa. `scripts/eval_report_sale.py` scores the "Sells your data" check at 0.88 accuracy, but on the same 137 training rows the rules were written against, whose labels are AI-drafted and not yet reviewed.

## User evidence

User-testing session was recorded this week. From the user-testing we understand:
- The "Sells your data" check said "Yes" for a policy that states "We do not sell personal information for monetary compensation". Two of its three quotes were wrong: one was a denial that the rules misread because of curly quotes ("we do not “sell”…"), and one was a description of the user's right to know.
- The model-confidence panel shows raw scores and cutoffs.
- The JSON export isn't useful to users.
- Save my policies needs work.

## New week's Goal

- **Fix the "Sells your data" check:** read denials with quote marks, skip sentences that only describe user rights, and add an in-between answer for "not for money, but ad cookies may count as a sale".
- **Measure the report card on held-out data:** human-review the sale-v1 validation and test rows, then score the check on those instead of the training rows.
- **Fair model comparison:** score the earlier ten-category RoBERTa, merged into the five classes, on the same OPP-115 test, to see whether the extra data helped.
- **App clean-up:** replace the raw confidence numbers with plain wording, remove the JSON export, and fix "My policies".
- **Browser extension:** carried over from last week; not started.

## Individual Contributions

1. Swetha: Reviewed the five-class dataset and training (split integrity, leakage checks, validation-only threshold selection) and compiled this weekly report.
2. Hamshika: Built the five-class conversion and cleaning scripts and the combined dataset in PR [#61](https://github.com/Hamshika06/Inkwell/pull/61), and merged PRs #61 and #62.
3. Sreya: Trained and evaluated the five-class RoBERTa (3 seeds) in PR [#62](https://github.com/Hamshika06/Inkwell/pull/62).
4. Aniruddhan: Built Inkwell 1.1, with the report card, decision bar, steps, My policies and the new home page, in PR [#63](https://github.com/Hamshika06/Inkwell/pull/63).
5. Gowtham S: Actively working on the risk score metric and brainstormed the classification approach with the team.