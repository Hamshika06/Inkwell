---
team: Token Economy
session: Session 8
date: 10/27/2026
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

_Week of October 26, 2026. The items below were merged to `main` today._

- **New frontend and user testing.** PR [#39](https://github.com/Hamshika06/Inkwell/pull/39) adds the new frontend, deployment configuration, and a Week 7 user-testing recording.
- **PolicyIE preprocessing.** PR [#43](https://github.com/Hamshika06/Inkwell/pull/43) adds preprocessing and a mapping for 31 policies. It retains 690 paragraphs (560 train, 130 test), including 226 paragraphs with none of the covered categories; all reported checks passed.
- **Reviewed C3PA v2 data and frozen dataset v2.** PR [#45](https://github.com/Hamshika06/Inkwell/pull/45) cleans and reviews the C3PA data, freezes the combined dataset, and records the data manifest. The reviewed C3PA set has 20,195 units; after removing 170 OPP-115 text duplicates, the combined classifier set has 23,754 rows.
- **DistilBERT combined-data run.** PR #45 also adds a DistilBERT run on dataset v2. Its validation results are 0.811 macro-F1 and 0.802 micro-F1. These are validation metrics, not test results.
- **Risk scoring.** Worked on a rule-based risk score and supporting documentation in PR [#40](https://github.com/Hamshika06/Inkwell/pull/40).

## User evidence

User-testing feedback is documented in [issue #42](https://github.com/Hamshika06/Inkwell/issues/42). The session recording is [Inkwell Week 7 user testing](../User%20Testing/Week%207/Recording/Inkwell-1.1_Week7_UserTesting_SurendhraKumar_Aniruddhan.mp4).

**The user liked:**

- The “Common Questions” section.
- Seeing each sentence tagged and color-coded.
- The overall UI and filtering system.
- Learning that a sentence can belong to two categories.

**The user wants changed or clarified:**

- The product appears to create an account when given invalid credentials.
- Explain how each category affects the user.

## New week's Goal

- Fix the account flow so invalid credentials cannot create an account unexpectedly.
- Explain the user impact of each category in the interface.
- Compare the DistilBERT v2 validation results with existing combined-data runs, then evaluate the selected model on the held-out test set.
- Decide whether PolicyIE should be integrated into training and evaluation; document how its categories map to the shared schema.
- Review the remaining user-testing feedback and prioritize frontend changes.
- Revisit risk scoring only after deciding how to validate its rules and thresholds with annotated examples.

## Individual Contributions

1. Aniruddhan: Contributed the frontend and user-testing work in PR [#39](https://github.com/Hamshika06/Inkwell/pull/39).
2. Swetha: Added PolicyIE preprocessing and its category mapping in PR [#43](https://github.com/Hamshika06/Inkwell/pull/43).
3. Hamshika: Cleaned and reviewed C3PA v2, froze dataset v2, and added the DistilBERT run in PR [#45](https://github.com/Hamshika06/Inkwell/pull/45).
4. Gowtham S: Opened PR [#40](https://github.com/Hamshika06/Inkwell/pull/40) for risk scoring.
5. Sreya: Drafted this weekly report.
