# Privacy document detection examples

The fetcher recognizes policy pages from page text and URL evidence. It also uses
the page's heading or title when a page is shorter than the general policy-text
threshold. A matching title alone is not enough: the page must contain at least
400 characters and at least two privacy-language matches. This helps with
shorter pages whose URL does not contain `privacy`, while rejecting title-only
and low-content pages.

## Regression examples

These synthetic fixtures cover alternate document wording found in privacy
policies. They exercise both link discovery from a site page and direct reading
of a short policy page.

| Example | Expected detector behavior | Result |
| --- | --- | --- |
| `Privacy Notice` at `/privacy-notice` | Find as a policy link | Found |
| `Your Privacy Statement` at `/legal/privacy` | Find as a policy link | Found |
| `Notice of Privacy Practices` at `/privacy` | Find as a policy link | Found |
| `Data Protection Notice` at `/data-protection` | Find as a policy link | Found |
| `Acme | Privacy Notice` at `/legal`, with policy-language body text | Read directly as a policy page | Found |
| `Privacy Notice` title with no body | Do not treat as a policy | Rejected |
| `Privacy Notice` title with short, generic body | Do not treat as a policy | Rejected |

## Measured result

The updated detector found **5 of 5 positive examples (100%)**: four link-label
variants and one short titled page. It rejected **2 of 2 negative examples**.
These are synthetic regression fixtures, not a measurement of recall across
real websites. The score means that the implemented behavior matches this small
example set; it does not establish broad real-world detection accuracy.

Run the focused regression suite from the repository root:

```sh
python3 -m unittest api.tests.test_fetcher -v
```
