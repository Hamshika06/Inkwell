# Sale-v2 training annotation audit

The supplied training file passes the structural audit. The machine-readable
results and input hash are in [train.annotation_audit.json](train.annotation_audit.json).
No annotation or source file was changed by the audit.

| Check | Result |
| --- | ---: |
| Training records, unique IDs, original membership | 7,379 |
| Annotated records | 278 |
| Unannotated records | 7,101 |
| Annotated paragraphs with no listed practices | 37 |
| Practices | 321 |
| Verified evidence/context spans | 722 |
| Structural issues | 0 |

All source fields match the combined snapshot. The unannotated review objects
match the original empty defaults. Of the unannotated rows, 7,100 also match
their initial serialized bytes exactly. The final row, `goppc:train:991`, differs
only by a missing final newline. Its JSON content is unchanged.

## Practice and actor fields

`actor` is accepted as the explicit field name; no rename is needed. Observed
values are `first_party`, `service_provider`, `third_party_ad_network`,
`third_party_advertiser`, `bankruptcy_court` and `data_reseller`.

| Practice | Permitted | Denied | Conditional | Unclear |
| --- | ---: | ---: | ---: | ---: |
| sale | 11 | 63 | 37 | 10 |
| rental | 4 | 13 | 20 | 3 |
| advertising_sharing | 23 | 5 | 8 | 0 |
| business_transfer | 1 | 0 | 123 | 0 |

All 278 annotated records cover these four practice types. The checked-negative
records retain explanatory notes; no evidence was invented for an absent
practice. All conditional practices have condition/exception evidence, and all
unclear practices have explanations.

The annotation draft groups `lend`/`license` with rental and `trade`/`swap`/
`exchange` with sale. These are operational annotation conventions, not
universal equivalences. Preserve the original verb and data scope in evidence;
a software license, product exchange or fraud-prevention information exchange
does not automatically establish the intended data-sale/rental practice.

The next model must retain the actor distinction. A `sale/denied` statement
about a service provider must not become a denial about the first party.
The sale-v1 trainer's practice/polarity targets do not capture that distinction
and cannot be reused unchanged. Actor coverage also needs an explicit modeling
definition before absent actor-specific targets are treated as negative.

Advertising annotations currently include both first-party disclosure and
direct third-party collection. Define whether these are one umbrella practice
or separate operations. Record the discloser/collector and recipient roles
consistently; actor names alone can otherwise mix different meanings.

## Remaining advertising candidate coverage

These counts apply only to the 7,101 unannotated training rows:

| Retrieval filter | Candidate paragraphs |
| --- | ---: |
| Advertising words or ad-network phrases | 728 |
| Cookie words | 685 |
| Union of both filters | 1,147 |
| Additional cookie-only candidates | 419 |

The broad union pattern is:

```regex
\badvertis\w*|\bad[ -]networks?\b|\bcookies?\b
```

It retrieves 568 OPP-115, 462 GoPPC and 117 PolicyIE paragraphs. These counts
describe candidates, not positives. Start with the 728 advertising/ad-network
hits, then examine cookie-only candidates and independently sampled nonmatches.
The selection bias in the existing 278 records means advertising recall cannot
be estimated for the entire training pool from those records alone.

Do not turn the other unannotated records into negative labels. Keep risk
coverage distinct from topic masks, and use validation under the same action,
actor and coverage definitions when measuring performance.

## Interpretation decisions to preserve

- `goppc:train:1558` and `goppc:train:6405`: distinguish advertising disclosure,
  a policy's sale terminology and the scope of its denial. Those statements
  are not automatically contradictory. Keep their evidence and qualifiers.
- `goppc:train:2945`: a qualified denial and a cross-reference to categories
  sold can coexist. Inspect the referenced context rather than treating the
  reference alone as proof that a sale occurred.
- `goppc:train:283`: the task should consistently capture what the policy
  states or permits, rather than infer actual business behavior. Template-like
  wording is still wording in the policy; retain uncertainty about unresolved
  purposes without assuming the statement is fictitious or observed conduct.
- Channel-partner marketing and reseller outreach: define whether disclosure
  for sales contact qualifies as `advertising_sharing`, or whether that label
  is limited to advertising networks/targeting. Apply the same rule to all
  records and evaluation data.

Structural validation cannot resolve these interpretation choices. Preserve
the draft labels and notes until the action, actor and operation definitions
are settled; do not silently rewrite the annotations or train on all 7,379 rows
as though their risk labels were complete.
