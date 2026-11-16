# Sale-v2: training, validation and test annotation audit

All three files pass the structural checks. The current input hashes, counts
and checks are in [splits.annotation_audit.json](splits.annotation_audit.json).
This report supersedes the earlier training-only audit for the current files;
the earlier report remains as a record of that annotation version.

| Split | Total records | Annotated | Unannotated | Checked negatives | Practices | Spans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 7,379 | 278 | 7,101 | 39 | 320 | 988 |
| Validation | 1,307 | 48 | 1,259 | 6 | 55 | 198 |
| Test | 1,731 | 77 | 1,654 | 17 | 79 | 244 |
| **Total** | **10,417** | **403** | **10,014** | **62** | **454** | **1,430** |

Checked negatives are annotated paragraphs with no listed practices and an
explanatory note. Span counts include evidence, scope, conditions, exceptions,
opt-outs and optional original-verb spans.

## Verified

- Every file parses as JSONL, with unique IDs and complete original split
  membership. The union contains all 10,417 source records.
- All source fields, text, labels, topic masks and metadata are unchanged.
- Source group IDs do not cross splits. This check does not independently
  establish cross-source company or template independence.
- Unannotated records retain the empty defaults. Annotated records have
  coverage, author/origin and notes where required.
- Practice types, actors, polarity labels and coverage agree structurally.
- Conditional labels have conditions or exceptions; unclear labels have
  practice-level explanations.
- Every evidence/context/verb span matches the paragraph at its exact offsets.
- Optional `recipient` fields are lists of distinct nonempty role strings.

## Updated practice representation

All annotated records cover these five practice types:

1. `sale`
2. `rental`
3. `advertising_disclosure`
4. `third_party_ad_collection`
5. `business_transfer`

`advertising_disclosure` and `third_party_ad_collection` replace the previous
umbrella `advertising_sharing` target in the current files. This distinction
must be retained in the next model rather than silently collapsed.

`actor` remains the field name. Optional `recipient` lists retain additional
party roles; optional `verbs` lists preserve original wording with exact
offsets. Vendor resale restrictions must not become first-party sale denials
when model targets are constructed.

## Coverage limits before training

The annotated subset is not the complete source dataset. Train only on known
practice targets, leaving the 10,014 unannotated paragraphs masked or excluded
from supervised risk training. Topic masks and risk-annotation coverage are
separate forms of supervision.

The initial train/validation development pool has 278 and 48 annotated
paragraphs respectively. The 77 annotated test paragraphs should be evaluated
only after the next model and decision rules are frozen; do not report metrics
over all 1,731 test rows as though every risk target were known.

Validation includes two `advertising_disclosure` propositions and no
`third_party_ad_collection` propositions. It cannot estimate recall for the
latter target. Earlier keyword-based selection also limits advertising
coverage. Expand validation through a declared, consistent selection protocol
before using it to compare that target.

The combined test pool includes 26 clauses previously evaluated in sale-v1.
Retain that exposure information and distinguish any newly independent cohort
from the full annotated test subset when reporting generalization.

No annotation was changed, and no model was trained or evaluated in this audit.
The subsequent [actor-aware, coverage-masked baseline](../../../Documentation/RISK_BASELINE_V2.md)
implements the target builder and has been trained and validated separately.
The sale-v1 trainer is incompatible with these `risk_review` records and must
not be used unchanged.
