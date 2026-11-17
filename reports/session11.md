---
team: Token Economy
session: Session 11
date: 11/17/2026
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

- **Browser extension and app improvements.** The extension can scan the current page and connect to Inkwell's analysis flow. The web app also received UI and progress updates. The extension is implemented, but its usefulness and reliability still need user validation.
- **Risk scoring and sale detection work.** The team added a TF-IDF baseline that predicts privacy practices, actors, and polarity while masking unknown annotation cells. On its frozen test subset, it reached 0.656 masked micro-F1 and 0.313 supported-target macro-F1 across 77 annotated paragraphs. First-party sale flags had 0.857 precision and 0.400 recall. The subset is small and selected, and the model has not been integrated into live risk scoring.
- **Held-out evaluation for the sale baseline.** The separate sale-v1 test evaluation covers 26 reviewed records. It reports 0.737 joint micro-F1 and 0.769 F1 for first-party sale flags. This measures agreement with the annotations on that cohort; it does not establish performance across all policies.
- **Risk scoring behavior updated.** The risk engine's scoring rules and points were revised, and a verdict scorer was added. Risk weights and bands remain experimental and are not calibrated estimates of harm.
- **Account and product flow updates.** The account menu gained a delete-account option, and a product review flow was integrated.
- **User testing.** Feedback from Srinidhi and Sriram was summarized. Both testers found Inkwell useful for understanding privacy policies and identifying concerns users might otherwise miss. The browser extension also worked on niche sneaker websites.

## User evidence

- **Participants:** Srinidhi and Sriram evaluated Inkwell's privacy-policy analysis tool.
- **Positive feedback:** Both testers found the product useful for understanding privacy policies and spotting potential concerns. They praised its core functionality, clear instructions, and ease of use. The browser extension worked on niche sneaker websites.
- **Desktop layout and colors:** On a 34-inch monitor, the interface remained centered and felt too much like a mobile layout. Sriram suggested using desktop screen space more effectively and refining the color palette.
- **Refresh experience:** Srinidhi noticed a brief blank area in the landing-page report card during refresh and suggested a loading animation, placeholder, or smoother transition.
- **Document detection:** Inkwell may miss policies titled with alternative terms such as “Privacy Notice.” Srinidhi suggested expanding detection to cover variations in document titles and wording.
- **Proactive alerts:** Srinidhi suggested notifying users when critical privacy concerns are detected, so they can take action without manually checking the extension.
- **Suggested priorities:** Improve privacy-document detection and explore critical-issue alerts first, followed by fixing the refresh blank state, improving desktop responsiveness, and refining colors. These priorities are recommendations based on the feedback, not rankings assigned by the testers.

## New week's Goal

- Expand privacy-document detection to recognize names such as “Privacy Notice,” and explore alerts for critical privacy issues.
- Fix the report-card blank state during refresh and improve the desktop layout and color palette based on user feedback.
- Improve the sale-practice baseline's recall and annotation coverage while preserving the frozen test results.
- Integrate practice and polarity evidence into risk scoring only after defining how uncertainty and evidence will be shown.
- Reassess the risk points and verdict wording with users; document that scores are screening indicators, not calibrated risk probabilities.
- Continue product cleanup based on user feedback, including saved policies and the analysis report.

## Individual Contributions

1. Aniruddhan: Added browser-extension and UI updates, integrated the product review flow, added the account deletion option, and recorded user-testing sessions.
2. Gowtham S: Built the sale-practice baseline and frozen test evaluation, and updated the risk-scoring engine.
3. Swetha: Updated risk points and added a verdict scorer.
4. Hamshika: Merged the five-class dataset/model and product updates from the previous week.
5. Sreya: Drafted this weekly report.
