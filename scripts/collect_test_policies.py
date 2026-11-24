"""Save the test-set policies with the app's own reader, so labellers see exactly the text Inkwell sees.

Usage (from the repository root):
    python scripts/collect_test_policies.py

Reads  data/test_policies/companies.csv   policy_id, company, homepage, policy_url (policy_url may be empty)
Writes data/test_policies/text/<policy_id>.txt
       data/test_policies/policies.csv    the link that was saved, its "last updated" date and the status

With policy_url empty, the reader starts at the homepage and finds the policy link itself. Fill policy_url
to choose the page yourself (when the link it found is wrong, or the site could not be read).
A policy saved before is kept and never downloaded again; delete its text file to download it again.
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.fetcher import FetchError, looks_like_policy, read_policy

FOLDER = ROOT / "data/test_policies"
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE = rf"{MONTH}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{MONTH}\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}"
MIN_CHARS = 5000  # A real policy is far longer; shorter text is a menu or a "turn on JavaScript" page.
UPDATED = re.compile(rf"(?:last\s+(?:updated|revised|modified)|effective(?:\s+date)?|updated)\s*(?:on|as of)?\s*:?\s*({DATE})", re.I)


def fetch(row):
    """(policy_url, text) for one company."""
    if row["policy_url"].strip():
        result = read_policy(row["policy_url"].strip(), confirmed=True)
    else:
        result = read_policy(row["homepage"].strip())
        if result["status"] == "confirm":  # The homepage linked to a policy page: read that page.
            result = read_policy(result["url"], confirmed=True)
    text = result["text"]
    garbled = text.count("\ufffd") > len(text) / 100  # The site sent compressed bytes, which read as gibberish.
    if len(text) < MIN_CHARS or garbled or not looks_like_policy(text, result["url"]):
        raise FetchError(422, f"Doesn't read as a full policy ({len(text):,} characters). Put the policy link in policy_url, or swap the company.")
    return result["url"], text


def main():
    rows = list(csv.DictReader((FOLDER / "companies.csv").open(encoding="utf-8")))
    (FOLDER / "text").mkdir(parents=True, exist_ok=True)
    report = FOLDER / "policies.csv"
    before = {r["policy_id"]: r for r in csv.DictReader(report.open(encoding="utf-8"))} if report.exists() else {}
    out = []
    for row in rows:
        path = FOLDER / "text" / f"{row['policy_id']}.txt"
        old = before.get(row["policy_id"])
        if path.exists() and old and old["company"] == row["company"]:  # Saved before: keep the frozen copy.
            out.append(old)
            print(f"{row['policy_id']} {row['company']}: kept the saved copy")
            continue
        try:
            url, text = fetch(row)
        except FetchError as e:
            out.append({**row, "last_updated": "", "saved_on": "", "n_chars": 0, "status": e.detail})
            print(f"{row['policy_id']} {row['company']}: FAILED - {e.detail}")
            continue
        path.write_text(text, encoding="utf-8")
        found = UPDATED.search(text)
        out.append({**row, "policy_url": url, "last_updated": found.group(1) if found else "",
                    "saved_on": date.today().isoformat(), "n_chars": len(text), "status": "ok"})
        print(f"{row['policy_id']} {row['company']}: saved {len(text):,} characters from {url}")
    with report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"\n{sum(r['status'] == 'ok' for r in out)} of {len(out)} saved. Check data/test_policies/policies.csv.")


if __name__ == "__main__":
    main()