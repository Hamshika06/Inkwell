---
team: Token Economy
session: Session 7
date: 10/20/2026
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

_Week of October 19, 2026. Everything below is merged to `main`. The app is live at https://inkwell-846713605562.us-east1.run.app/._

- **RoBERTa trained on combined OPP-115 + C3PA data.** First run with `--source combined` (seed 42, C3PA loss weight 0.1, learning rate 2e-5). Early stopping ended it after 4 epochs (best epoch 2), about 2 hours of training on a Colab GPU. On the OPP-115 test set it scores **0.669 macro-F1 / 0.744 micro-F1**, below the OPP-115-only RoBERTa (0.740 / 0.800).   
- **Web app now serves the combined RoBERTa.** The API loads `roberta-c3pa-opp115-seed42` from the Hugging Face weights repo.  (evidence: [PR #37](https://github.com/Hamshika06/Inkwell/pull/37))
- **Web UI redesign and sign-in.** New layout with summary tiles, a topic overview that marks topics with no matching clause as "Not mentioned", and light and dark themes. A login page offers Google, GitHub and email sign-in through Firebase; when sign-in is configured, the API rejects analyses without a valid token. (evidence: [PR #37](https://github.com/Hamshika06/Inkwell/pull/37))
- **Product usage guide.** [`USAGE_README.md`](../USAGE_README.md) covers the live demo, the three models with their speed per paragraph, and what the results show. (evidence: [PR #31](https://github.com/Hamshika06/Inkwell/pull/31))

## New week's Goal

- **Decide which RoBERTa the app serves.** Our evaluation rule selects on validation, and the OPP-115-only run (0.865) beats the combined run (0.812). Either justify the combined model or switch back.
- **Train DistilBERT on the combined data** to complete the head-to-head.
- **Modern benchmark table.** Put every model's C3PA positive-label recall (lookup-table mapping, 5 categories) in one table in `Documentation/EXPERIMENTS.md`, including the combined run.
- **Update README and EXPERIMENTS.md.** Both still say the C3PA runs are pending.

## Individual Contributions

1. Swetha: Contributed to discussions on model tuning, logged this week's results, and compiled this weekly report.
2. Hamshika: Organized the repository, and reviewed and merged PRs [#31](https://github.com/Hamshika06/Inkwell/pull/31), [#33](https://github.com/Hamshika06/Inkwell/pull/33) and [#37](https://github.com/Hamshika06/Inkwell/pull/37).
3. Aniruddhan: Redesigned the web UI, added Firebase sign-in to the page and the API, and switched the app to the combined RoBERTa ([PR #37](https://github.com/Hamshika06/Inkwell/pull/37)); wrote the product usage guide ([PR #31](https://github.com/Hamshika06/Inkwell/pull/31)). Reviewed and merged PRs [#34](https://github.com/Hamshika06/Inkwell/pull/34) and [#35](https://github.com/Hamshika06/Inkwell/pull/35).
4. Sreya: Fine-tuned and uploaded the combined RoBERTa run results ([PR #33](https://github.com/Hamshika06/Inkwell/pull/33), [PR #34](https://github.com/Hamshika06/Inkwell/pull/34)).
5. Gowtham S: Coordinated dataset combination and model tuning across the team, and reviewed PRs.