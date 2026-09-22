---
team: Token Economy
session: Session 4
date: 11/22/2026
members:
  - name: Hamshika Radhakrishnan
    github: Hamshika06
    hat: Engineering
  - name: Swetha Rathinavelu Saravanakumar	
    github: <handle>
    hat: Data&Eval
  - name: Sreya Nagulapati
    github: <handle>
    hat: User & Research
  - name: Aniruddhan Narasimhan
    github: <handle>
    hat: Product
  - name: Gowtham S
    github: <handle>
    hat: Operations
north_star:
  metric: Number of contracts correctly analyzed
  value: 0
  previous: 0
---

## Features

1. **Important deadlines:**
Agreement Date, Effective Date, Expiration Date, Renewal Term, Notice Period to Terminate Renewal

2. **Confidentiality & NDAs:**
Confidentiality clauses, Non-Disparagement

3. **Non-competes & restrictions:**
Non-Compete, Exclusivity, No-Solicit of Customers, No-Solicit of Employees, Non-Transferable License

4. **Liability exposure:**
Cap on Liability, Uncapped Liability, Liquidated Damages, Insurance, Warranty Duration


## Data Source

We would be using the CUAD dataset for this project <br>
[Contract Understanding Atticus Dataset (CUAD)](https://www.atticusprojectai.org/cuad) consists of 500 contracts with annotations for 41 legal clauses. This dataset provides a rich source of legal text for information extraction and analysis.

## Problem Statement

Small service businesses sign contracts constantly (vendor agreements, client MSAs and SOWs, NDAs, leases) but rarely have the budget or in-house legal team to review them properly. Traditional legal review costs **$200–500 an hour** and takes days, so routine contracts often get signed unread, or reviewed too late to negotiate anything.

AI contract-review tools like **ClauseGuard** lower that cost by using LLMs to flag risky clauses in under a minute. But they still leave three gaps open:

1. **Generic benchmarks.** Every contract is scored against generic industry red flags, not against what's actually normal for that specific business.
2. **Abstract output.** Results come as a 0–100 risk number instead of a concrete dollar consequence or deadline someone can act on.
3. **No institutional memory.** Nothing is learned from the business's own negotiation history, so the same leverage gets re-discovered, or missed, every time.

**Inkwell** is built to close these gaps: a contract intelligence system that grounds every judgment in the business's own historical agreements and negotiation outcomes, and reports material findings in **dollars and deadlines** rather than abstract risk scores.

## Individual Contributions

1. Aniruddhan: Formulating problem statement
2. Swetha: Identifying the dataset required
3. Sreya: Researched existing tools and published pain points from legal-tech articles/forums to identify who struggles with contract review and why, so Product has real evidence instead of guesses to define the target user and value proposition. Users will be recruited through UMD entrepreneurship and law student group.
4. Gowtham S. Create the GitHub Project Kanban board, create tasks for individual contributors, communicating with the team members to create the report
5. Hamshika: Set up the project repo, environment, and a basic pipeline skeleton (data loading → model → inference) so the team has something to plug real components into as they're built.
