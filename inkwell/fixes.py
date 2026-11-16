"""Where to go to limit a practice, instead of emailing the company.

Three sources, best first:
  1. "known": a short hand-checked list of big sites, with direct links to their own privacy switches.
  2. "policy": links found on the policy page itself ("Do Not Sell My Info", "Cookie settings", "Delete your account").
  3. "industry": ad-industry opt-out pages that switch off targeted ads from many ad companies at once.
Each fix says which kind of practice it limits, so a report line can point at the right one.
"""
import re
from urllib.parse import urlsplit

I = re.IGNORECASE

# kind -> what the link limits. Order matters: the first pattern that matches a link wins.
KINDS = (
    ("sale", "Stop the sale or sharing of your data",
     re.compile(r"\bdo\s*not\s*(?:sell|share)|\bdon['’]?t\s+sell|\byour\s+privacy\s+choices\b|\bopt[- ]?out\s+of\s+(?:the\s+)?(?:sale|sharing)\b|"
                r"\blimit\s+the\s+use\s+of\s+my\s+sensitive|do-not-sell|donotsell|privacy-choices", I)),
    ("delete", "Delete your account or data",
     re.compile(r"\bdelet\w*\s+(?:your\s+|my\s+)?(?:account|data|personal|information)|\b(?:close|deactivate|erase)\s+(?:your\s+|my\s+)?account\b|"
                r"\bdata\s+deletion\b|\baccount\s+deletion\b|delete-account|delete-my", I)),
    ("ads", "Turn off targeted ads",
     re.compile(r"\bad(?:vertising|s)?\s+(?:preferences|settings|choices|centre|center)\b|\binterest[- ]based\s+(?:ads|advertising)\b|"
                r"\bopt[- ]?out\s+of\s+(?:targeted|personali[sz]ed|interest[- ]based)?\s*(?:ads|advertising)\b|\bpersonali[sz]ed\s+ads\b|"
                r"\bad\s*choices\b|adprefs|ad[-_]settings|ads[-_]preferences", I)),
    ("cookies", "Change cookie and tracking settings",
     re.compile(r"\bcookie\s+(?:settings|preferences|choices|consent)\b|\bmanage\s+cookies\b|\btracking\s+(?:settings|preferences)\b", I)),
    ("rights", "Request, download or correct your data",
     re.compile(r"\b(?:privacy|data|subject\s+access|consumer)\s+(?:request|requests|portal|rights\s+request)\b|\bdownload\s+(?:your|my)\s+(?:data|information)\b|"
                r"\baccess\s+(?:your|my)\s+(?:data|information)\b|\bexercise\s+your\s+(?:privacy\s+)?rights\b|\bdsar\b|privacy-request|data-request", I)),
    ("settings", "Open your privacy settings",
     re.compile(r"\bprivacy\s+(?:settings|controls|dashboard|center|centre|hub|choices)\b|\bmanage\s+(?:your\s+)?privacy\b|"
                r"\baccount\s+settings\b|privacy-settings|privacy-center|privacycentral", I)),
)
LABELS = {kind: label for kind, label, _ in KINDS}

# Hand-checked direct links to the switches themselves, keyed by the site's name part ("google" for google.co.uk).
# Checked 2026-11-14 signed out: each loads, or goes to sign-in and then back to it (Facebook and LinkedIn refuse
# automated checks). Before adding a link, open it signed in and find the switch; leave a kind out rather than guess.
KNOWN = {
    "google": {"ads": "https://myadcenter.google.com/", "settings": "https://myaccount.google.com/data-and-privacy",
               "delete": "https://myaccount.google.com/delete-services-or-account", "rights": "https://takeout.google.com/"},
    "youtube": {"ads": "https://myadcenter.google.com/", "settings": "https://myaccount.google.com/data-and-privacy",
                "rights": "https://takeout.google.com/"},
    "facebook": {"ads": "https://accountscenter.facebook.com/ad_preferences", "settings": "https://accountscenter.facebook.com/",
                 "rights": "https://accountscenter.facebook.com/info_and_permissions/dyi"},
    "instagram": {"ads": "https://accountscenter.instagram.com/ad_preferences", "settings": "https://accountscenter.instagram.com/",
                  "rights": "https://accountscenter.instagram.com/info_and_permissions/dyi"},
    "microsoft": {"ads": "https://account.microsoft.com/privacy/ad-settings", "settings": "https://account.microsoft.com/privacy"},
    "apple": {"rights": "https://privacy.apple.com/", "delete": "https://privacy.apple.com/"},
    "amazon": {"ads": "https://www.amazon.com/adprefs"},
    "linkedin": {"ads": "https://www.linkedin.com/mypreferences/d/categories/ads",
                 "settings": "https://www.linkedin.com/mypreferences/d/categories/privacy",
                 "rights": "https://www.linkedin.com/mypreferences/d/download-my-data"},
    "x": {"ads": "https://x.com/settings/ads_preferences", "settings": "https://x.com/settings/privacy_and_safety",
          "rights": "https://x.com/settings/download_your_data", "delete": "https://x.com/settings/deactivate"},
    "twitter": {"ads": "https://x.com/settings/ads_preferences", "settings": "https://x.com/settings/privacy_and_safety",
                "rights": "https://x.com/settings/download_your_data", "delete": "https://x.com/settings/deactivate"},
    "reddit": {"settings": "https://www.reddit.com/settings/privacy"},
    "spotify": {"settings": "https://www.spotify.com/account/privacy/"},
}
# Industry pages: switch off interest-based ads from many participating ad companies at once (not the site itself).
INDUSTRY = (
    {"kind": "ads", "label": "Ad industry opt-out (Digital Advertising Alliance)", "url": "https://optout.aboutads.info/", "source": "industry"},
    {"kind": "ads", "label": "Ad industry opt-out (Network Advertising Initiative)", "url": "https://optout.networkadvertising.org/", "source": "industry"},
)


def site_key(url):
    """"https://www.google.co.uk/x" -> "google"."""
    labels = (urlsplit(url).hostname or "").lower().removeprefix("www.").split(".")
    if len(labels) >= 3 and labels[-2] in ("co", "com", "org", "net", "ac", "gov", "edu"):
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else labels[0]


def classify(text, href):
    """The kind of practice a link limits, or None."""
    probe = f"{text} {href}"
    return next((kind for kind, _, rx in KINDS if rx.search(probe)), None)


def fix_links(links, page_url, limit=8):
    """[{kind, label, url, source}] for a policy page: hand-checked site links first, then links on the page.
    links: (text, href) pairs from the page; mailto links are left to the report's request emails."""
    out, seen = [], set()
    same_page = _plain(page_url)

    def add(kind, url, source, text=None):
        key = (kind, _plain(url))
        if key in seen or len(out) >= limit:
            return
        seen.add(key)
        out.append({"kind": kind, "label": LABELS[kind], "url": url, "source": source, **({"text": text} if text else {})})

    for kind, url in KNOWN.get(site_key(page_url), {}).items():
        add(kind, url, "known")
    for text, href in links:
        if not href.lower().startswith(("http://", "https://")) or len(text) > 120:
            continue
        if _plain(href) == same_page:  # A jump to another section of the policy, not a settings page.
            continue
        kind = classify(text, href)
        if kind:
            text = text.strip().strip("'\"‘’“”")
            add(kind, href, "policy", None if GENERIC.fullmatch(text) else text or None)
    return out


GENERIC = re.compile(r"(?:click\s+)?here|this\s+(?:page|link|form)|link|learn\s+more|more|read\s+more", I)


def _plain(url):
    """The address without its #section or trailing slash, for spotting duplicates and same-page links."""
    return url.split("#")[0].rstrip("/").lower()
