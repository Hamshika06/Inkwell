---
team: Token Economy
session: Session 12
date: 11/24/2026
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

- **Interactive Guides and extension installation.** PR [#80](https://github.com/Hamshika06/Inkwell/pull/80) replaces the Guides page with a “Behind the I agree button” explorer. Five topics explain reading a policy, sharing with partners, data sales, user rights, and deletion through sample wording and report-card examples. It also adds a downloadable extension ZIP, a packaging script, and instructions for loading the extension in Chrome, Edge, and Brave.
- **A frozen 40-policy evaluation set.** PR [#81](https://github.com/Hamshika06/Inkwell/pull/81) adds 40 saved policy texts, a collection manifest, and a script that uses the app's own policy reader. The script preserves saved copies and rejects short or garbled responses. The PR reports that none of the selected companies appear in C3PA or OPP-115. Labelling rules cover all eight report-card questions and require exact supporting sentences. This prepares a policy-level evaluation; final labels and a scoring script are still pending, so there is no new accuracy result.
- **Broader privacy-document detection.** PR [#82](https://github.com/Hamshika06/Inkwell/pull/82) recognizes alternatives including “Privacy Notice,” “Privacy Statement,” “Notice of Privacy Practices,” and “Data Protection Notice.” Short pages with matching titles still need sufficient body text and privacy-language evidence. The documented regression fixtures find all five positive examples and reject both negative examples. These are synthetic examples, not a measurement of detection accuracy across real websites.
- **Visual reports and clearer analysis flow.** PR [#83](https://github.com/Hamshika06/Inkwell/pull/83) adds a 3D landing-page example, guided onboarding, an animated analysis screen, explanations of privacy terms, and a “Where your data goes” map with supporting policy quotes in the app and extension. Reports and saved-policy views gain visual exposure indicators and links to relevant action steps. The exposure count falls when users mark steps complete; this records their checklist actions and does not verify that a company has changed its data practices.
- **Pasted-policy handling.** PR [#83](https://github.com/Hamshika06/Inkwell/pull/83) also strips HTML from pasted page source, splits long text blocks into paragraphs, and asks users whether to continue when text appears to be non-English, terms of service, or unrelated content. These checks are heuristics and still need validation with varied real inputs.

## User evidence

No new user-testing session was added during this reporting period. Last week's feedback from Srinidhi and Sriram remains the basis for follow-up work:

- **Alternative document titles:** PR #82 directly addresses the report that policies named “Privacy Notice” could be missed. The regression examples confirm the intended detection behavior, but user validation is still needed.
- **Layout and loading:** PR #83 changes the landing-page presentation and analysis transitions. The changes have not yet been shown to resolve the reported 34-inch desktop layout or refresh blank-state issues.
- **Critical-issue alerts:** Proactive notifications remain a proposed feature; these PRs do not establish that they were implemented.

## New week's Goal

- Agree on the three open labelling decisions in the test-set rules: conflicting statements, rights limited to particular regions, and notice given only by posting an updated policy.
- Have each team member label eight of the frozen policies, recording exact evidence for all eight questions. Resolve disagreements and save the agreed answers in `data/test_policies/labels.csv`.
- Add a scoring script and evaluate the report card against those labels. Report per-question errors and distinguish this policy-level evaluation from the earlier paragraph-classification results.
- Validate the new policy-title detection on real websites and retest the desktop layout, refresh behavior, onboarding, and extension installation with users.
- Check whether users understand the data map and exposure indicators, especially that completing a request does not prove the request has been fulfilled.
- Revisit proactive critical-issue alerts and prioritize them alongside the remaining user-feedback fixes.

## Individual Contributions

1. Hamshika: Redesigned the Guides page and added extension packaging, download, and installation instructions in PR [#80](https://github.com/Hamshika06/Inkwell/pull/80).
2. Swetha: Collected the 40-policy test set and added the collection script, manifest, and labelling rules in PR [#81](https://github.com/Hamshika06/Inkwell/pull/81).
3. Sreya: Expanded privacy-document detection, added regression examples, and documented their results in PR [#82](https://github.com/Hamshika06/Inkwell/pull/82).
4. Aniruddhan: Added the visual report and UI changes, data maps, onboarding, analysis transitions, and pasted-input improvements in PR [#83](https://github.com/Hamshika06/Inkwell/pull/83).
5. Gowtham S: Co-ordinated the tasks for this week and compiled this week's report. Also, working on re-designing the UI to accomodate risk score.
