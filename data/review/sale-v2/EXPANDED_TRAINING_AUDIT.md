# Expanded training annotations

The expanded training file passes the existing actor-aware loader's structural,
source-identity, coverage and span checks. The combined source and split
membership are unchanged. The audit is in
[expanded_training.annotation_audit.json](expanded_training.annotation_audit.json).

| Measure | Previous training version | Expanded training version |
| --- | ---: | ---: |
| Annotated paragraphs | 278 | 1,126 |
| Unannotated paragraphs | 7,101 | 6,253 |
| Checked-negative paragraphs | 39 | 541 |
| Practice propositions | 320 | 709 |
| Advertising disclosure propositions | 29 | 206 |
| Third-party ad-collection propositions | 5 | 213 |

The expansion adds 848 annotated paragraphs. Current practice totals are sale
121, rental 42, advertising disclosure 206, third-party ad collection 213 and
business transfer 127. All remaining unannotated risk targets stay unknown.

## Validation expansion remains outstanding

The validation file is byte-identical to the previous run's validation input.
It still has 48 annotated paragraphs, with two advertising-disclosure
propositions and no third-party ad-collection propositions. Consequently it
cannot estimate ad-collection recall or support reliable model selection for
that practice. Test annotations are also unchanged, and no model was fitted or
evaluated in this audit.

Among the 1,259 unannotated validation paragraphs, the following text-only
filters retrieve candidates:

| Filter | Candidate paragraphs |
| --- | ---: |
| Advertising words or ad-network phrases | 118 |
| Advertising/ad-network phrases or cookies | 176 |

These are retrieval candidates, not positive labels. Expand validation using a
declared selection protocol consistent with the training annotation scope,
including permissions, denials, conditional wording and checked negatives.
Include non-keyword sampling when assessing coverage beyond the filter.

Rare affirmative targets also remain sparse: first-party sale permitted has 11
training propositions, and first-party rental permitted has five. The expanded
advertising counts do not resolve every target's support gap.

## Next run

After updating validation, rerun the actor-aware, coverage-masked baseline into
a new run directory. Compare on development data while retaining the previous
checkpoint and recorded test results. The current saved baseline still reflects
the earlier 278-paragraph training subset; it was not silently updated.

The frozen evaluator is expected to reject current training annotations against
the previous run's training hash. That is a provenance check, not a reason to
replace the old run's hashes or overwrite its measurements. Future revisions
need a separately declared final evaluation protocol.
