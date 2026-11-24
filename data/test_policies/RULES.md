# Test set labelling rules

Read the whole policy, then answer all 8 questions. For each answer, copy the proof
sentence exactly from the .txt file (no rewording). For "Not mentioned", leave the proof empty.

## The 8 questions and the allowed answers

| # | Question | Allowed answers |
|---|---|---|
| 1 | Sells your data | Yes / Says they don't / Says they don't, with exceptions / Only if you agree / Only if the company is sold / Not mentioned |
| 2 | Uses your data for targeted ads | Yes / Says they don't / Not mentioned |
| 3 | Shares your data with other companies | Yes / Says they don't / Not mentioned |
| 4 | Collects your location | Yes / Says they don't / Not mentioned |
| 5 | Says how long it keeps your data | Keeps some data indefinitely / States a time limit / Time limit for some data only / No clear time limit / Not mentioned |
| 6 | Lets you delete your data | Yes / Says you can't / Not mentioned |
| 7 | Lets you opt out | Yes / Says you can't / Not mentioned |
| 8 | Tells you before the policy changes | Yes, they'll tell you / Can change it without telling you / Not mentioned |

## Rules for tricky cases

1. Selling means giving data for money **or anything of value**. "In exchange for", "may be
   considered a sale", and "sharing for cross-context behavioural advertising" (California's
   wording) all count as Yes.
2. Describing a right is not a sale. "You have the right to opt out of the sale of your
   information" doesn't say they sell. Answer Q1 from other sentences; it does count for Q7.
3. A merger or acquisition clause alone ("if we are acquired, your data may transfer") is
   "Only if the company is sold", not Yes.
4. "As long as necessary" with no end date is "No clear time limit". If some data has an end
   date and the rest doesn't, it's "Time limit for some data only".
5. Cookies or pixels used for ads count as targeted ads (Q2 Yes).
6. Sharing with service providers (payment, hosting, delivery) counts as sharing (Q3 Yes).
7. A "Do Not Sell or Share" link counts as an opt-out (Q7 Yes).

## Decisions still open (team to agree before labelling)

A. The policy says both Yes and No for the same question. Suggested: the riskier answer wins.
B. A right only applies to some people ("California residents may opt out"). Suggested: answer
   Yes and add a note "California only".
C. "We'll post changes on this page" with no other notice. Suggested: "Can change it without
   telling you", because nobody is told directly.

## Labelling sheet columns

policy_id, question, answer, proof sentence, note, labelled by, changed after AI check (yes/no)