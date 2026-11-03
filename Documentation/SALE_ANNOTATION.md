# Sale-practice annotation: recovered OPP-115 data

Start with [the training review queue](../data/review/sale-v1/REVIEW.md).
It shows the original policy text, annotator identifiers, polarity values and
action spans. All target labels are deliberately blank: recovered OPP labels
are not equivalent to the four proposed sale labels.

## What was recovered

The original OPP-115 v1 archive was downloaded from the
[Usable Privacy Policy Project](https://usableprivacy.org/data). Its annotations
are available for research, teaching and scholarship; follow the source terms
and citation requirements when reusing them.

The existing preprocessing retains category labels and four extraction attribute
types: Personal Information Type, Third Party Entity, Purpose and Retention
Period. The review exporter recovers **all original attributes** for each
candidate, including Does/Does Not, Action Third Party, Choice Type and Choice
Scope. This preserves annotation-level associations instead of merging an
entire paragraph's attributes into one inferred sale practice.

The source category XML establishes two important limits:

- `Does/Does Not` defaults to `Does`. It is not necessarily an explicit positive
  assertion, and cannot directly become a `permitted` sale label.
- `Action Third Party` has no dedicated sale value. Sale wording may appear in
  a highlighted action span labelled `Receive/Shared with` or another value.

Every original attribute value and selected-text/offset object is retained.
Usable attribute spans are checked against the raw sanitized segment and mapped
to the same cleaned text used by frozen v1. A mismatch is repaired only if the
selected text occurs exactly once. Known errant, unmatched or ambiguous spans
have no usable `span`; the original value is still visible for review.

## Batch contents

The batch contains **182 candidate segments from 100 policies**, drawn from the
3,663 retained frozen OPP-115 segments:

| File | Segments | Purpose |
| --- | ---: | --- |
| `data/review/sale-v1/train.jsonl` | 137 | Develop guidelines and training annotations |
| `data/review/sale-v1/validation.jsonl` | 18 | Evaluate development choices |
| `data/review/sale-v1/test.jsonl` | 27 | Final evaluation after choices are fixed |
| `data/review/sale-v1/candidates.jsonl` | 182 | Read-only source snapshot for validation |

The exporter searched sell/sold/selling/resell/resold/sale/sales wording without
a category filter. Product sales, sales representatives and asset-sale references
are intentional candidate false positives. Implicit sales and paraphrases that
use none of these words are missed: **this queue is not a complete sale benchmark**.
Add independently sampled policies and nonmatching clauses before measuring
general sale-detection recall. Do not interpret the candidate distribution as a
population prevalence estimate.

The manifest records source/dataset/schema/output hashes, the source attribute
schema, split counts and span statuses: 5,930 exact, 13 uniquely repaired,
74 known errant, 18 unmatched and 5,024 unselected attribute entries. Multiple
annotations can come from one annotator; their counts are not independent votes.

Original frozen policy/company splits are retained. Quarantined or dropped rows
are not reintroduced. Existing benchmark files and the live risk scorer are
unchanged by this extraction.

## Annotate the training file

1. Copy `train.jsonl` to a working file, for example `train.reviewed.jsonl`.
   Keep the original batch files unchanged. Each line is one JSON object.
2. Read the full paragraph, using the original policy context when references
   or exceptions require it. The raw sanitized segment is included as
   `raw_segment`.
3. Fill in `review.sale_related`. Use `false` for a candidate that does not
   concern sale of personal information, with a reason in `review.notes`.
   Missing annotations do not mean false.
4. For a sale-related candidate, add one or more scoped propositions to
   `review.practices`. Each requires `label`, `evidence`, `conditions`,
   `exceptions` and `notes`. Use the definitions in
   [the annotation schema](../configs/sale_annotation_schema.json).
5. Record two distinct human identifiers in `reviewer` and `adjudicator` after
   review. An AI suggestion, if used during annotation, needs human checking;
   it is not an independent human judgment.

Practice object example, for the illustrative text
`We sell your data only with consent.` (not a new gold training example):

```json
{
  "label": "conditional",
  "evidence": [{"start": 0, "end": 36, "text": "We sell your data only with consent."}],
  "conditions": [{"start": 18, "end": 35, "text": "only with consent"}],
  "exceptions": [],
  "notes": "Sale permission is qualified by consent."
}
```

All offsets are zero-based Python character offsets into the **cleaned `text`**,
with exclusive ends. Never copy raw HTML offsets into the review evidence.
Evidence must include enough text to retain the actor, practice, information and
scope; a keyword such as `sell` alone is insufficient for interpretation.

For example, a denial limited to third-party marketing should retain that
purpose in its evidence. A paragraph with a denial and an exception must retain
the exception; a separate unrelated sharing permission must not turn the sale
denial into a permitted sale. An opt-out is not equivalent to prior consent.
For `unclear`, explain the semantic ambiguity; do not use it for an unreviewed row.

Validate a completed subset or the full reviewed file:

```sh
python -m scripts.sale_review validate \
  --batch data/review/sale-v1 \
  --reviewed data/review/sale-v1/train.reviewed.jsonl \
  --out data/review/sale-v1/train.accepted.jsonl
```

Validation rejects changed source fields, duplicate/unknown IDs, unreviewed
records, missing reviewer identifiers, invalid labels, mismatched spans,
conditional labels without conditions/exceptions and unexplained unclear labels.
It does not determine whether a semantic judgment is correct. Output includes a
provenance manifest; existing outputs are never overwritten. Do not train on
`candidates.jsonl` or regard the source attributes as final sale labels.

## Reproduce the extraction

Download the archive using the source dataset page, then run from the project
root with the existing research dependencies installed:

```sh
python -m scripts.sale_review export \
  --root /tmp/inkwell-opp115-v1.zip \
  --out data/review/sale-v2
```

Use a new output directory to avoid overwriting review work. The archive itself
is not added to the repository. Run `python -m unittest discover -s tests -v`
for span-mapping, export, provenance and review-validation checks.
