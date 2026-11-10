"""Privacy report card: plain-language checks with polarity, each backed by exact sentences.

Every check reads sentences, not whole paragraphs, so "We do not sell your data" and "Sharing for ads
may count as a sale" in the same policy are told apart. A check's verdict is one of:
  found    - the policy says the company does it
  denied   - the policy says the company doesn't
  missing  - nothing in the text addresses it (not proof either way)
plus check-specific states for retention and policy changes. Wording-based and deterministic: no model
output enters a verdict, and nothing is generated. Evidence offsets index the submitted text.
"""
import re
from dataclasses import dataclass

VERSION = "1.1.0"
I = re.IGNORECASE

# Negation in the same sentence: "we do not / don't / never / will not ... <verb>".
NOT = r"(?:do(?:es)?\s+not|don['’]?t|doesn['’]?t|never|will\s+not|won['’]t|shall\s+not|(?:have|has)\s+not|cannot)"
# An exception turns a denial back into a yes: "we do not share ... except with our partners".
EXCEPTION = re.compile(r"\b(?:except|unless|other\s+than|apart\s+from|with\s+the\s+(?:\w+\s+)?exceptions?|"
                       r"without\s+your\s+(?:\w+\s+)?(?:consent|permission))\b", I)
# Names of opt-out links ("Do Not Sell or Share My Personal Information") must not read as a denial.
LINK_NAMES = re.compile(r"[\"“']?do\s+not\s+(?:sell|share)(?:\s+(?:or|and|/)\s+(?:sell|share))?\s+my\s+(?:personal\s+)?(?:info(?:rmation)?|data)[\"”']?", I)


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    kind: str              # "risk": found is bad. "right": found is good.
    found: tuple           # Sentence patterns meaning "they do it".
    denied: tuple = ()     # Sentence patterns meaning "they say they don't".
    strip_link_names: bool = False


def _rx(*patterns):
    return tuple(re.compile(p, I) for p in patterns)


DATA = r"(?:data|information|info)"
CHECKS = (
    Check("sale", "Sells your data", "risk", ()),  # Scored by sale() below.
    Check("ads", "Uses your data for targeted ads", "risk",
          _rx(r"\b(?:targeted|interest[- ]based|personali[sz]ed|behaviou?ral|tailored|cross[- ]context)\s+(?:ads|advertis\w*)",
              r"\badvertis\w*\s+(?:partners?|networks?|companies|providers?)\b",
              r"\b(?:share|disclose|provide|sell)\w*\b[^.;]{0,80}\badvertis\w*",
              r"\b(?:ads|advertis\w*)\b[^.;]{0,40}\b(?:based\s+on|tailored\s+to)\s+(?:your|you)\b"),
          _rx(NOT + r"\s+(?:\w+\s+){0,2}(?:use|share|sell|disclose|show|serve)\b[^.;]{0,60}\b(?:ads|advertis\w*)",
              r"\bno\s+(?:third[- ]party\s+)?(?:ads|advertising)\b"),
          strip_link_names=True),
    Check("sharing", "Shares your data with other companies", "risk",
          _rx(r"\b(?:share|disclose|provide|transfer|make\s+available|pass)\w*\b[^.;]{0,100}\b(?:third[- ]part\w*|partners?|affiliates?|vendors?|"
              r"service\s+providers?|other\s+companies|advertisers?|data\s+brokers?)\b",
              r"\b(?:third[- ]part\w*|partners?|advertisers?)\b[^.;]{0,60}\b(?:receive|collect|access)\w*\b[^.;]{0,40}\b" + DATA),
          _rx(NOT + r"\s+(?:\w+\s+){0,2}(?:share|disclose|rent|trade|provide|transfer)\b"),
          strip_link_names=True),
    Check("location", "Collects your location", "risk",
          _rx(r"\b(?:precise|gps|geo-?location|geolocation|location\s+(?:data|information|services)|your\s+location|approximate\s+location)\b"),
          _rx(NOT + r"\s+(?:\w+\s+){0,2}(?:collect|track|use|store)\w*\b[^.;]{0,40}\blocation\b")),
    Check("delete", "Lets you delete your data", "right",
          _rx(r"\b(?:you\s+(?:can|may|could)|you\s+have\s+the\s+right\s+to|right\s+to|ask\s+us\s+to|request\s+(?:that\s+we\s+)?)(?:[^.;]{0,60})\b(?:delet\w*|eras\w*)\b",
              r"\b(?:request|requests|right)\b[^.;]{0,30}\b(?:deletion|erasure)\b", r"\bdeletion\s+requests?\b"),
          _rx(r"\b(?:cannot|can\s*not|can['’]t|unable\s+to|not\s+able\s+to)\s+(?:\w+\s+){0,3}(?:delete|erase)\b")),
    Check("optout", "Lets you opt out", "right",
          _rx(r"\bopt(?:[- ]?out|ing\s+out)\b", r"\bunsubscribe\b", r"\bwithdraw\s+(?:your\s+)?consent\b",
              r"\bdo\s+not\s+(?:sell|share)(?:\s+or\s+share)?\s+my\b", r"\byour\s+privacy\s+choices\b",
              r"\b(?:turn|switch)\s+off\b[^.;]{0,40}\b(?:ads|advertis\w*|tracking|personali[sz]\w*|location|cookies)\b"),
          _rx(r"\b(?:cannot|can['’]t|not\s+able\s+to|unable\s+to)\s+opt[- ]?out\b")),
)

# ---------- Sale: its own rules, measured against the reviewed sale-v1 set (scripts/eval_report_sale.py) ----------

PERSONAL = r"(?:data|information|info|details|e-?mails?|e-?mail\s+address\w*|addresses|names|(?:customer|user|mailing|postal|marketing|subscriber)\s+lists?)"
SALE_FOUND = _rx(
    r"\b(?:sell|rent)(?:s|ing)?\b[^.;]{0,100}\b" + PERSONAL + r"\b",
    r"\b" + PERSONAL + r"\b[^.;]{0,60}\b(?:sold|rented)\b",
    r"\b" + PERSONAL + r"\b[^.;]{0,40}\bwe\s+(?:may\s+)?(?:sell|rent)\b",
    r"\bconstitut\w*\s+(?:a\s+)?[\"“']?(?:sale|selling)\b", r"\bconsidered\s+(?:a\s+)?[\"“']?(?:sale|selling)\b",
    r"\bsale\s+of\s+(?:your\s+)?personal\b")
# Things that aren't personal data: "we do not sell products to children" is not about your data.
NOT_DATA = r"(?![^.;]{0,40}\b(?:products?|goods|items|merchandise|tickets|services|alcohol|tobacco)\b)"
SALE_DENIED = _rx(
    NOT + r"\s+(?:and\s+will\s+not\s+)?(?:[\w,]+\s+){0,3}(?:sell|rent)\w*\b" + NOT_DATA,
    r"\bnot\s+(?:be\s+|been\s+)?(?:[\w,]+\s+){0,3}(?:sold|rented)\b",
    r"\bnot\s+(?:authori[sz]ed|permitted|allowed)\s+to\s+(?:[\w,]+\s+){0,3}(?:sell|rent)\b",
    r"\b(?:restricted|prohibited)\s+from\s+(?:[\w,]+\s+){0,3}(?:selling|renting)\b",
    r"\bnot\s+(?:the|our)\s+policy\b[^.;]{0,40}\bto\s+(?:sell|rent)\b",
    r"\b(?:no|none\s+of\s+(?:the|your))\s+(?:\w+\s+){0,3}(?:information|data)\b[^.;]{0,60}\b(?:will|is|are|shall)\s+(?:be\s+)?(?:\w+\s+){0,2}(?:sold|rented)\b",
    r"\bnot\s+in\s+the\s+business\s+of\s+selling\b", r"\b(?:have|has)\s+not\s+sold\b")
# After a denial: exceptions that still mean "no sale" (a payment processor, the law) versus ones that open the door.
# "Except as described in this policy": the exceptions are somewhere else, so it isn't a plain no.
ELSEWHERE = re.compile(r"\b(?:as|where)\s+(?:\w+\s+)?(?:described|outlined|explained|set\s+(?:forth|out)|stated|provided|noted|"
                       r"disclosed|listed|detailed)\b|\bexceptions?\s+(?:that\s+)?(?:we\s+)?(?:explain|describe|list)\w*\b|\bbelow\b", I)
CONSENT = re.compile(r"\b(?:consent|permission|opt(?:s|ed)?[- ]?in|you\s+(?:agree|choose|direct|ask|authori[sz]e))\b", I)
HARMLESS = re.compile(r"\b(?:service\s+providers?|payment|credit\s+card|process\w*|vendors?|contractors?|agents?|law|legal\w*|"
                      r"required|court|subpoena|affiliat\w*|subsidiar\w*|internal\w*)\b", I)
# "If we are acquired, your information may be among the transferred assets": in nearly every policy, and not a sale.
BUSINESS = re.compile(r"\b(?:merg(?:er|ed|e)|acquisition|acquired\s+by|bankrupt\w*|insolvenc\w*|reorgani[sz]ation|divestiture|"
                      r"change\s+(?:in|of)\s+(?:ownership|control)|corporate\s+(?:transaction|structure|change)|business\s+transfers?|"
                      r"(?:sale|transfer)\s+of\s+(?:all|some|part|a\s+portion|substantially)|(?:transferred|business)\s+assets|"
                      r"among\s+the\s+(?:transferred\s+)?assets|(?:buy|sell)\s+(?:or\s+(?:buy|sell)\s+)?(?:various|certain|some|all)?\s*"
                      r"(?:of\s+(?:our|its)\s+)?(?:assets|business(?:es)?|stores|units))\b", I)


def _exception_kind(phrase):
    """What an exception to "we don't sell" amounts to: consent, harmless (still no sale), elsewhere, or open."""
    if CONSENT.search(phrase):
        return "consent"
    if ELSEWHERE.search(phrase):
        return "exceptions"
    return "denied" if HARMLESS.search(phrase) else "found"


def sale(sents):
    found, denied, exceptions, consent, transfer = [], [], [], [], []
    for seg, a, b, text in sents:
        evidence = _evidence(seg, a, b, text)
        if BUSINESS.search(text):
            transfer.append(evidence)
            continue
        probe = LINK_NAMES.sub(" ", text)
        denial = next((m for rx in SALE_DENIED for m in [rx.search(probe)] if m), None)
        if denial:
            before, after = probe[:denial.start()], probe[denial.end():]
            late, early = EXCEPTION.search(after), EXCEPTION.search(before)
            # An exception after the denial runs to the end of the sentence; one before it ends at the denial.
            kind = (_exception_kind(after[late.start():]) if late else
                    _exception_kind(before[early.start():]) if early else "denied")
            {"found": found, "denied": denied, "exceptions": exceptions, "consent": consent}[kind].append(evidence)
        elif any(rx.search(probe) for rx in SALE_FOUND):
            found.append(evidence)
    if found:
        return _verdict("sale", "found", found, denied + consent)
    if denied:
        return _verdict("sale", "denied", denied, transfer)
    if exceptions:
        return _verdict("sale", "exceptions", exceptions, transfer)
    if consent:
        return _verdict("sale", "consent", consent, transfer)
    if transfer:
        return _verdict("sale", "transfer", transfer)
    return _verdict("sale", "missing", [])


RETAIN = re.compile(r"\b(?:retain\w*|retention|keep|keeps|kept|store|stored|storage\s+period|delete[sd]?|deletion|purge[sd]?)\b", I)
# "In the 12 months prior to ..." is a reporting window (CCPA disclosures), not how long data is kept.
LOOKBACK = re.compile(r"\b(?:in|during|over|for)\s+the\s+(?:past|prior|preceding|last|previous)\s+(?:\w+\s+){0,2}(?:months?|years?)\b|"
                      r"\b(?:\d+|twelve)\s*(?:\(\d+\)\s*)?months?\s+(?:prior|preceding|before)\b", I)
RESPONSE = re.compile(r"\b(?:respond|response|reply|replies|process\s+your\s+request)\b", I)
PERIOD = re.compile(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|eighteen|twenty[- ]four|thirty|sixty|ninety)"
                    r"\s*(?:\(\d+\)\s*)?(?:days?|weeks?|months?|years?)\b", I)
FOREVER = re.compile(r"\b(?:indefinitely|forever|permanently|without\s+(?:a\s+)?time\s+limit|for\s+an\s+unlimited\s+(?:time|period))\b", I)
VAGUE = re.compile(r"\b(?:as\s+long\s+as|for\s+the\s+(?:period|time)\s+(?:necessary|needed|required)|no\s+longer\s+than\s+(?:is\s+)?necessary|"
                   r"as\s+(?:needed|necessary|required)|until\s+(?:you|it\s+is\s+no\s+longer))\b", I)
CHANGE = re.compile(r"\b(?:chang\w*|updat\w*|modif\w*|revis\w*|amend\w*)\b", I)
POLICY = re.compile(r"\b(?:policy|policies|statement|notice|terms)\b", I)
NOTIFY = re.compile(r"\b(?:notify|notifying|inform|email|e-mail|alert|contact)\w*\s+you\b|\b(?:prior|advance|prominent)\s+notice\b|"
                    r"\bnotice\s+(?:to\s+you|by\s+email)\b|\bask\s+for\s+your\s+consent\b", I)
SILENT_CHANGE = re.compile(r"\bwithout\s+(?:prior\s+|advance\s+|any\s+)?(?:notice|notifying|notification)\b|"
                           r"\b(?:continued|continuing)\s+use\b[^.;]{0,100}\b(?:accept\w*|agree\w*|consent\w*|acknowledg\w*|bound)\b", I)

# What each verdict means for the reader. tone: bad / good / unknown.
VERDICTS = {
    "sale": {"found": ("bad", "Yes, or it may count as a sale", "Your information can go to other companies in exchange for money or other value. In several US states you can tell them to stop."),
             "denied": ("good", "Says they don't", "The policy states they don't sell your information."),
             "exceptions": ("unknown", "Says they don't, with exceptions", "They say they don't sell, except in cases described elsewhere in the policy. Read those cases in the full breakdown."),
             "consent": ("good", "Only if you agree", "They say they won't sell your information unless you give permission."),
             "transfer": ("unknown", "Only if the company is sold", "They don't describe selling your data, but it would go to a new owner if the company is sold or merged. Almost every policy says this."),
             "missing": ("unknown", "Not mentioned", "The policy doesn't say either way. Look for a “Do Not Sell” link or ask them.")},
    "ads": {"found": ("bad", "Yes", "What you do is used to choose the ads you see, often with help from ad companies."),
            "denied": ("good", "Says they don't", "The policy says your data isn't used for targeted ads."),
            "missing": ("unknown", "Not mentioned", "No mention of targeted ads in the text you pasted.")},
    "sharing": {"found": ("bad", "Yes", "Other companies get some of your information. Who matters: advertisers and data brokers are a bigger deal than a payment processor."),
                "denied": ("good", "Says they don't", "The policy says your information stays with them."),
                "missing": ("unknown", "Not mentioned", "The policy doesn't say who else gets your data.")},
    "location": {"found": ("bad", "Yes", "They know roughly, or exactly, where you are."),
                 "denied": ("good", "Says they don't", "The policy says they don't collect your location."),
                 "missing": ("unknown", "Not mentioned", "No mention of location data.")},
    "delete": {"found": ("good", "Yes", "You can ask them to delete your information."),
               "denied": ("bad", "Says you can't", "The policy limits or refuses deletion."),
               "missing": ("unknown", "Not mentioned", "The policy doesn't say you can delete your data. Depending on where you live, you may still have that right.")},
    "optout": {"found": ("good", "Yes", "You can turn some of this off. The steps are under “Your steps”."),
               "denied": ("bad", "Says you can't", "The policy says you can't opt out."),
               "missing": ("unknown", "Not mentioned", "No opt-out described in the text you pasted.")},
    "retention": {"forever": ("bad", "Keeps some data indefinitely", "Some of your data may never be deleted."),
                  "limit": ("good", "States a time limit", "They say how long they keep your data."),
                  "mixed": ("unknown", "Time limit for some data only", "Some data has an end date; the rest is kept “as long as necessary”, which they decide."),
                  "vague": ("unknown", "No clear time limit", "“As long as necessary” means they decide how long. No end date is given."),
                  "missing": ("unknown", "Not mentioned", "The policy doesn't say how long your data is kept.")},
    "changes": {"silent": ("bad", "Can change it without telling you", "They can change the rules, and keeping on using the service counts as agreeing."),
                "notify": ("good", "Yes, they'll tell you", "You'll be notified before important changes."),
                "missing": ("unknown", "Not mentioned", "The policy doesn't say how you'll hear about changes.")},
}
TITLES = {"retention": "Says how long it keeps your data", "changes": "Tells you before the policy changes"}
ORDER = ("sale", "ads", "sharing", "location", "retention", "delete", "optout", "changes")


def sentences(segments):
    """Yield (segment, start, end, text) for each sentence, offsets into the submitted text."""
    for seg in segments:
        text, cursor = seg["text"], 0
        for brk in re.finditer(r"(?<=[.!?])[\"”')\]]*\s+(?=[\"“(\[]?[A-Z0-9•\-])|\n+", text):
            yield from _piece(seg, text, cursor, brk.start())
            cursor = brk.end()
        yield from _piece(seg, text, cursor, len(text))


def _piece(seg, text, a, b):
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    if b - a > 3:
        yield seg, seg["start"] + a, seg["start"] + b, text[a:b]


def _evidence(seg, start, end, text):
    return {"segment_id": seg["id"], "start": start, "end": end, "text": text}


def _unique(evidence):
    seen = set()
    return [e for e in evidence if not (e["text"] in seen or seen.add(e["text"]))]


def _verdict(check_id, state, evidence, counter=()):
    tone, label, meaning = VERDICTS[check_id][state]
    evidence, counter = _unique(evidence), _unique(counter)
    check = next((c for c in CHECKS if c.id == check_id), None)
    return {"id": check_id, "title": check.title if check else TITLES[check_id], "state": state, "tone": tone,
            "label": label, "meaning": meaning, "evidence": list(evidence)[:3], "evidence_count": len(evidence),
            "counter": list(counter)[:2]}


def run_check(check, sents):
    found, denied = [], []
    for seg, a, b, text in sents:
        probe = LINK_NAMES.sub(" ", text) if check.strip_link_names else text
        if any(p.search(probe) for p in check.denied):
            (found if EXCEPTION.search(probe) else denied).append(_evidence(seg, a, b, text))
        elif any(p.search(probe) for p in check.found):
            found.append(_evidence(seg, a, b, text))
    if found:
        return _verdict(check.id, "found", found, denied)
    return _verdict(check.id, "denied", denied) if denied else _verdict(check.id, "missing", [])


def retention(sents):
    hits = {"forever": [], "limit": [], "vague": []}
    for seg, a, b, text in sents:
        if not RETAIN.search(text) or RESPONSE.search(text):
            continue
        if FOREVER.search(text) and not re.search(NOT + r"\b[^.;]{0,40}\b(?:indefinitely|forever|permanently)", text, I):
            hits["forever"].append(_evidence(seg, a, b, text))
        elif PERIOD.search(LOOKBACK.sub(" ", text)):
            hits["limit"].append(_evidence(seg, a, b, text))
        elif VAGUE.search(text):
            hits["vague"].append(_evidence(seg, a, b, text))
    if hits["forever"]:
        return _verdict("retention", "forever", hits["forever"], hits["limit"] + hits["vague"])
    if hits["limit"] and hits["vague"]:
        return _verdict("retention", "mixed", hits["limit"], hits["vague"])
    for state in ("limit", "vague"):
        if hits[state]:
            return _verdict("retention", state, hits[state])
    return _verdict("retention", "missing", [])


def changes(sents):
    silent, notify = [], []
    for seg, a, b, text in sents:
        if not (CHANGE.search(text) and POLICY.search(text)):
            continue
        if SILENT_CHANGE.search(text):
            silent.append(_evidence(seg, a, b, text))
        elif NOTIFY.search(text):
            notify.append(_evidence(seg, a, b, text))
    if silent:
        return _verdict("changes", "silent", silent, notify)
    return _verdict("changes", "notify", notify) if notify else _verdict("changes", "missing", [])


# ---------- "What you can do": links, addresses and settings the policy itself gives ----------

URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'()\[\]]+[^\s<>\"'()\[\].,;:!?]", I)
EMAIL = re.compile(r"\b[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
SETTINGS = re.compile(r"\b(?:Settings|Preferences|Account|Privacy|Profile)(?:\s*(?:>|›|→|»)\s*[A-Z][\w&' -]{1,30}?(?=\s*(?:>|›|→|»|[,.;)]|\s+(?:and|or|to|in|on|page|menu|tab|section)\b|$)))+")
NAMED_LINK = re.compile(r"[\"“]?(?:Do\s+Not\s+Sell(?:\s+or\s+Share)?\s+My\s+Personal\s+Information|Your\s+Privacy\s+Choices|Limit\s+the\s+Use\s+of\s+My\s+Sensitive\s+Personal\s+Information)[\"”]?", I)
ACTION_KINDS = (
    ("optout", "Opt out of ads, sale or sharing",
     re.compile(r"\bopt(?:[- ]?out|ing\s+out)\b|\bdo\s+not\s+(?:sell|share)\b|\bunsubscribe\b|\badvertis|\bcookie|\bwithdraw\s+(?:your\s+)?consent|\bprivacy\s+choices\b|\bmarketing\b", I)),
    ("rights", "Get a copy of your data, or have it deleted",
     re.compile(r"\bdelet|\beras|\baccess\b|\bcopy\b|\bcorrect|\bportab|\brights?\b|\brequest", I)),
    ("contact", "Ask their privacy team a question",
     re.compile(r"\bprivacy\b|\bdata\s+protection\b|\bquestions?\b|\bcontact\b|\bconcerns?\b|\bcomplain", I)),
)


def actions(sents):
    found, seen = [], set()
    for seg, a, b, text in sents:
        targets = []
        for m in URL.finditer(text):
            value = m.group()
            targets.append({"kind": "url", "value": value if value.lower().startswith("http") else "https://" + value})
        targets += [{"kind": "email", "value": m.group()} for m in EMAIL.finditer(text)]
        targets += [{"kind": "settings", "value": m.group().strip()} for m in SETTINGS.finditer(text)]
        targets += [{"kind": "named_link", "value": m.group().strip("\"“” ")} for m in NAMED_LINK.finditer(text)]
        if not targets:
            continue
        kind = next(((k, title) for k, title, rx in ACTION_KINDS if rx.search(text)), None)
        if kind is None:
            continue
        fresh = [t for t in targets if (kind[0], t["value"].lower()) not in seen]
        if not fresh:
            continue
        seen.update((kind[0], t["value"].lower()) for t in fresh)
        found.append({"type": kind[0], "title": kind[1], "targets": fresh[:3], "evidence": _evidence(seg, a, b, text)})
    rank = {k: i for i, (k, _, _) in enumerate(ACTION_KINDS)}
    found.sort(key=lambda x: rank[x["type"]])
    return found[:6]


def policy_title(segments):
    """The first paragraph when it reads like a heading, e.g. "Pigeonpost Privacy Policy"."""
    if not segments:
        return None
    first = segments[0]["text"].strip()
    if len(first) <= 90 and "\n" not in first and not first.endswith((".", ":", ";")) and re.search(r"\b(?:privacy|policy|notice|statement)\b", first, I):
        return first
    return None


# ---------- Plan: which practices apply, and which the policy itself lets you switch off ----------

# Whether a verdict means the practice applies to you (True), doesn't (False) or isn't settled by the text (None).
# Stated as fact, not judgment: the reader decides what matters through their own priorities.
APPLIES = {
    "sale": {"found": True, "denied": False, "consent": False},
    "ads": {"found": True, "denied": False},
    "sharing": {"found": True, "denied": False},
    "location": {"found": True, "denied": False},
    "retention": {"forever": True, "vague": True, "mixed": True, "limit": False},
    "delete": {"denied": True, "found": False},
    "optout": {"denied": True, "found": False},
    "changes": {"silent": True, "notify": False},
}
# How each practice reads when it applies, for the decision summary.
CONCERN = {
    "sale": "Can sell your data", "ads": "Uses your data for targeted ads", "sharing": "Shares your data with other companies",
    "location": "Collects your location", "retention": "No end date for keeping your data", "delete": "Limits deleting your data",
    "optout": "Says you can't opt out", "changes": "Can change the policy without telling you",
}
# Which kinds of step can switch each practice off. "request" steps are emails to the policy's privacy address.
REMEDIES = {
    "sale": ("optout_link", "request_optout"),
    "ads": ("optout_link", "request_optout"),
    "sharing": ("optout_link", "request_optout"),
    "location": ("tip_location",),
    "retention": ("rights_link", "request_delete"),
}
NOTES = {
    "sharing": "Usually only partly: companies that run the service for them still get your data.",
    "location": "General advice for any app, not something this policy says.",
    "retention": "Deleting your data, or your account, is the way to put an end date on it.",
}


def _privacy_email(found_actions):
    """The policy's privacy address: from a rights or opt-out sentence first, then any contact sentence."""
    rank = {"rights": 0, "optout": 1, "contact": 2}
    emails = [(rank[a["type"]], "privacy" not in t["value"].lower(), t["value"])
              for a in found_actions for t in a["targets"] if t["kind"] == "email"]
    return min(emails)[2] if emails else None


def steps(checks, found_actions):
    """Concrete things to do, each traceable to the policy (or marked as general advice)."""
    by_id = {c["id"]: c for c in checks}
    out = []
    for a in found_actions:
        kind = {"optout": "optout_link", "rights": "rights_link"}.get(a["type"])
        if not kind:
            continue
        for t in a["targets"]:
            if t["kind"] == "email":
                continue  # Emails become pre-written requests below.
            title = (f"Use “{t['value']}” on their website" if t["kind"] == "named_link" else
                     f"Change it in {t['value']}" if t["kind"] == "settings" else
                     "Open the opt-out link the policy gives" if kind == "optout_link" else "Open the request link the policy gives")
            out.append({"id": f"{kind}-{len(out)}", "kind": kind, "title": title, "target": t,
                        "source": "policy", "segment_id": a["evidence"]["segment_id"]})
    email = _privacy_email(found_actions)
    if email:
        wants_optout = any(APPLIES[i].get(by_id[i]["state"]) for i in ("sale", "ads", "sharing"))
        if wants_optout:
            out.append({"id": "request_optout", "kind": "request_optout", "template": "optout", "to": email, "source": "policy",
                        "title": "Ask them to stop selling or sharing your data"})
        out.append({"id": "request_delete", "kind": "request_delete", "template": "delete", "to": email, "source": "policy",
                    "title": "Ask them to delete your data"})
        out.append({"id": "request_access", "kind": "request_access", "template": "access", "to": email, "source": "policy",
                    "title": "Ask for a copy of your data"})
    if by_id["location"]["state"] == "found":
        out.append({"id": "tip_location", "kind": "tip_location", "source": "general",
                    "title": "Turn off location access for this app or site",
                    "detail": "On your phone: Settings › Privacy › Location. In your browser: the site's permissions (lock icon)."})
    return out


def concerns(checks, plan_steps):
    """Each practice that applies: can the policy's own steps switch it off, or does it come with the service?"""
    out = []
    for c in checks:
        if not APPLIES[c["id"]].get(c["state"]):
            continue
        fixes = [st["id"] for st in plan_steps if st["kind"] in REMEDIES.get(c["id"], ())]
        out.append({"id": c["id"], "title": CONCERN[c["id"]], "fixable": bool(fixes), "steps": fixes, "note": NOTES.get(c["id"]) if fixes else None})
    return out


def company_name(title):
    """"Pigeonpost Privacy Policy (fictional sample)" -> "Pigeonpost"; None when there's no title."""
    if not title:
        return None
    name = re.split(r"\s[:|–—-]\s|:", re.sub(r"\(.*?\)", " ", title))[0]
    name = re.sub(r"\b(?:online\s+|global\s+|consumer\s+|customer\s+)?(?:privacy|data\s+protection|cookie)\s+(?:policy|notice|statement)\b|"
                  r"\b(?:policy|notice|statement)\b", " ", name, flags=I)
    name = re.sub(r"['’]s\b", "", re.sub(r"\s+", " ", name)).strip(" ,.")
    return name or None


def build_report(segments):
    sents = list(sentences(segments))
    by_id = {c.id: run_check(c, sents) for c in CHECKS if c.found}
    by_id["sale"] = sale(sents)
    by_id["retention"], by_id["changes"] = retention(sents), changes(sents)
    checks = [by_id[i] for i in ORDER]
    for c in checks:
        c["applies"] = APPLIES[c["id"]].get(c["state"])
    tally = {tone: sum(c["tone"] == tone for c in checks) for tone in ("bad", "good", "unknown")}
    found_actions = actions(sents)
    plan_steps = steps(checks, found_actions)
    title = policy_title(segments)
    return {"version": VERSION, "title": title, "company": company_name(title), "checks": checks, "tally": tally,
            "actions": found_actions, "steps": plan_steps, "concerns": concerns(checks, plan_steps),
            "limitation": "Wording-based checks, not legal advice. A verdict is only as good as the text you pasted: "
                          "paraphrases, exceptions and missing sections can change it. Read the quoted sentence."}
