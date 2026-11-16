"""Read a privacy policy from a link: fetch one public web page safely and turn it into paragraphs.

Safety: only http(s) on the standard ports, and every address a name resolves to must be public, checked again on
each redirect. The connection then goes to that checked address, so a name can't switch to an internal one after
the check. Size and time are capped. Nothing fetched is logged or stored.
"""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

MAX_BYTES = 3_000_000
MAX_SECONDS = 25
MAX_REDIRECTS = 5
MAX_PARAGRAPHS = 200
USER_AGENT = "Mozilla/5.0 (compatible; InkwellPolicyReader/1.0)"
MIN_POLICY_CHARS = 1500
MIN_CONFIRMED_CHARS = 400
I = re.IGNORECASE

COPY_IT = "Open the page, copy the policy text, and paste it here instead."


class FetchError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _public_ip(host, port):
    """The address to connect to. Refuses a name if any address it resolves to isn't public."""
    try:
        found = {info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except (socket.gaierror, UnicodeError):
        raise FetchError(422, "We couldn't find that website. Check the link and try again.")
    for raw in found:
        ip = ipaddress.ip_address(raw.split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global or ip.is_multicast:
            raise FetchError(400, "That address can't be read. Use a link to a public website.")
    if not found:
        raise FetchError(422, "We couldn't find that website. Check the link and try again.")
    return sorted(found)[0]


def _clean_url(url):
    """(scheme, host, port, path?query) for a link, or FetchError. A missing scheme means https."""
    url = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, I):
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError(400, "That doesn't look like a valid link.")
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise FetchError(400, "Only http and https links can be read.")
    if parts.username or parts.password:
        raise FetchError(400, "Links with a username or password can't be read.")
    default = 443 if parts.scheme.lower() == "https" else 80
    if port not in (None, default):
        raise FetchError(400, "Only links on standard web ports can be read.")
    try:
        host = parts.hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise FetchError(400, "That doesn't look like a valid link.")
    target = quote(parts.path or "/", safe="/%:@!$&'()*+,;=~-._") + (f"?{quote(parts.query, safe='%/:@!$&()*+,;=~-._?')}" if parts.query else "")
    return parts.scheme.lower(), host, default, target


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, **kw):
        super().__init__(host, **kw)
        self.pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, **kw):
        super().__init__(host, **kw)
        self.pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)


def _request(scheme, host, port, ip, target, deadline):
    """One GET to a checked address: (status, headers, body up to the size cap)."""
    conn = (_PinnedHTTPS if scheme == "https" else _PinnedHTTP)(host, ip, port=port, timeout=min(10, max(1, deadline - time.monotonic())))
    try:
        conn.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                                             "Accept-Language": "en", "Accept-Encoding": "identity"})
        response = conn.getresponse()
        body = bytearray()
        while len(body) <= MAX_BYTES and time.monotonic() < deadline:
            chunk = response.read(65536)
            if not chunk:
                break
            body += chunk
        if len(body) > MAX_BYTES:
            raise FetchError(422, f"That page is too large to read. {COPY_IT}")
        return response.status, response.headers, bytes(body)
    finally:
        conn.close()


@dataclass
class Page:
    url: str
    html: str
    content_type: str


def download(url, deadline):
    """Fetch a page, following redirects and re-checking the address at every hop."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if time.monotonic() >= deadline:
            raise FetchError(422, f"That website took too long to answer. {COPY_IT}")
        scheme, host, port, target = _clean_url(current)
        ip = _public_ip(host, port)
        try:
            status, headers, body = _request(scheme, host, port, ip, target, deadline)
        except FetchError:
            raise
        except ssl.SSLError:
            raise FetchError(422, f"That website's security certificate couldn't be verified. {COPY_IT}")
        except (OSError, http.client.HTTPException):
            raise FetchError(422, f"We couldn't reach that website. {COPY_IT}")
        if status in (301, 302, 303, 307, 308) and headers.get("Location"):
            current = urljoin(f"{scheme}://{host}{target}", headers["Location"])
            continue
        if status in (401, 403, 406, 429, 451, 503):
            raise FetchError(422, f"That website doesn't let automated readers in. {COPY_IT}")
        if status in (404, 410):
            raise FetchError(422, "That page doesn't exist. Check the link and try again.")
        if status != 200:
            raise FetchError(422, f"That website returned an error. {COPY_IT}")
        ctype = (headers.get("Content-Type") or "").lower()
        if ctype and not re.search(r"text/html|xhtml|text/plain", ctype):
            raise FetchError(422, f"That link isn't a web page (it may be a PDF). {COPY_IT}")
        charset = re.search(r"charset=[\"']?([\w-]+)", ctype) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], I)
        name = charset.group(1) if charset else "utf-8"
        name = name.decode("ascii", "replace") if isinstance(name, bytes) else name
        try:
            html = body.decode(name, "replace")
        except LookupError:
            html = body.decode("utf-8", "replace")
        return Page(f"{scheme}://{host}{target}", html, ctype)
    raise FetchError(422, f"That link redirects too many times. {COPY_IT}")


# ---------- HTML to paragraphs ----------

HARD_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "object", "canvas", "head"}
SOFT_SKIP = {"nav", "aside", "select", "button", "dialog"}
PAGE_FURNITURE = {"header", "footer"}  # Skipped outside <main>/<article>, where they hold site menus.
BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "dl", "dt", "dd", "table", "tr", "blockquote", "pre",
         "h1", "h2", "h3", "h4", "h5", "h6", "address", "figure", "details", "summary", "form", "fieldset", "center", "body"}
HEADING = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BANNER = re.compile(r"cookie[-_ ]?(?:banner|consent|notice|bar|popup)|onetrust|consent[-_ ]?(?:banner|manager)", I)
# Links whose address the report's steps need. Page text only says "click here", so the address is added in brackets.
ACTION_LINK = re.compile(r"opt[- ]?out|do not (?:sell|share)|your privacy choices|privacy (?:choices|settings|center|centre|request)|"
                         r"unsubscribe|ad (?:settings|preferences|choices)|adchoices|delete|deletion|data request|manage (?:your )?(?:data|cookies|preferences)", I)


@dataclass
class Extract:
    blocks: list = field(default_factory=list)   # (kind, text, in_main)
    links: list = field(default_factory=list)    # (text, href)
    title: str = ""
    h1: str = ""


class _Reader(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.out = base, Extract()
        self.buf, self.kind = [], "p"
        self.skip_tag, self.skip_depth, self.skip_hard = None, 0, False
        self.main_depth = 0
        self.in_title = False
        self.anchor = None  # [text parts, href]

    def _flush(self):
        text = "".join(self.buf)
        self.buf = []
        for piece in re.split(r"\n[ \t]*\n", text):
            piece = re.sub(r"\s+", " ", piece).strip()
            if piece:
                self.out.blocks.append((self.kind, piece, self.main_depth > 0))

    def _skip_because(self, tag, attrs):
        if tag in HARD_SKIP:
            return True
        # Inside the main content, "hidden" usually means a collapsed section of the policy, which we want.
        hidden = not self.main_depth and ("hidden" in attrs or attrs.get("aria-hidden") == "true" or re.search(r"display\s*:\s*none", attrs.get("style") or "", I))
        return bool(hidden or tag in SOFT_SKIP or (tag in PAGE_FURNITURE and not self.main_depth)
                    or attrs.get("role") in ("navigation", "banner", "contentinfo")
                    or BANNER.search(f"{attrs.get('id') or ''} {attrs.get('class') or ''}"))

    def handle_starttag(self, tag, attrs):
        attrs = {k: v for k, v in attrs}
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth += 1
            if tag == "a" and not self.skip_hard:
                self.anchor = [[], attrs.get("href") or ""]
            return
        if tag == "title":
            self.in_title = True
            return
        if tag not in VOID and self._skip_because(tag, attrs):
            self.skip_tag, self.skip_depth, self.skip_hard = tag, 1, tag in HARD_SKIP
            return
        if tag == "a":
            self.anchor = [[], attrs.get("href") or ""]
        elif tag == "br":
            self.buf.append("\n")
        elif tag in BLOCK:
            self._flush()
            self.kind = "h" if tag in HEADING else "li" if tag == "li" else "p"
            if tag in ("main", "article"):
                self.main_depth += 1

    def _close_anchor(self, in_body):
        text = re.sub(r"\s+", " ", "".join(self.anchor[0])).strip()
        href = self.anchor[1].strip()
        self.anchor = None
        lowered = href.lower()
        if lowered.startswith("mailto:"):
            address = href[7:].split("?")[0]
            self.out.links.append((text, href))
            if in_body and address and address not in text:
                self.buf.append(f" ({address})")
        elif href and not lowered.startswith(("#", "javascript:", "tel:")):
            full = urljoin(self.base, href)
            if not full.lower().startswith(("http://", "https://")):
                return
            self.out.links.append((text, full))
            if in_body and ACTION_LINK.search(f"{text} {href}") and full not in text:
                self.buf.append(f" ({full})")

    def handle_endtag(self, tag):
        if self.skip_tag:
            if tag == "a" and self.anchor:
                self._close_anchor(False)
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if not self.skip_depth:
                    self.skip_tag = None
                    self.anchor = None
            return
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.anchor:
            self._close_anchor(True)
        elif tag in BLOCK:
            self._flush()
            self.kind = "p"
            if tag in ("main", "article") and self.main_depth:
                self.main_depth -= 1

    def handle_data(self, data):
        if self.skip_tag:
            if self.anchor and not self.skip_hard:
                self.anchor[0].append(data)
            return
        if self.in_title:
            self.out.title += data
            return
        if self.anchor:
            self.anchor[0].append(data)
        self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def extract(html, base):
    reader = _Reader(base)
    reader.feed(html)
    reader.close()
    out = reader.out
    out.title = re.sub(r"\s+", " ", out.title).strip()
    out.h1 = next((t for k, t, _ in out.blocks if k == "h"), "")
    return out


def _merge(paragraphs, target):
    merged = []
    for text in paragraphs:
        if merged and len(merged[-1]) + len(text) < target:
            merged[-1] += "\n" + text
        else:
            merged.append(text)
    return merged


def to_text(doc):
    """Policy text with blank lines between paragraphs: headings join what follows, list items join their lead-in."""
    main = [b for b in doc.blocks if b[2]]
    blocks = main if sum(len(b[1]) for b in main) >= 800 else doc.blocks
    title = next((t for t in (doc.h1, doc.title) if t and len(t) <= 90 and re.search(r"privacy|policy|notice|statement", t, I)), "")
    paragraphs, heading, list_open = [], "", False
    for kind, text, _ in blocks:
        if text == title and not paragraphs and not heading:
            continue
        if kind == "h":
            heading = f"{heading}\n{text}" if heading else text
            list_open = False
            continue
        body = f"{heading}\n{text}" if heading else text
        joins_list = kind == "li" and paragraphs and not heading and (list_open or paragraphs[-1].endswith(":")) and len(paragraphs[-1]) + len(text) < 1200
        if joins_list:
            paragraphs[-1] += "\n" + text
        else:
            paragraphs.append(body)
        heading, list_open = "", kind == "li"
    if heading:
        paragraphs.append(heading)
    target = 700
    while len(paragraphs) > MAX_PARAGRAPHS - 1:  # The API reads at most MAX_PARAGRAPHS, title included.
        paragraphs = _merge(paragraphs, target)
        target = int(target * 1.5)
    return "\n\n".join(([title] if title else []) + paragraphs)


POLICY_WORDS = re.compile(r"personal (?:information|data)|your (?:information|data)|third[- ]part|cookies|we collect|privacy", I)


def looks_like_policy(text, url):
    hits = len(POLICY_WORDS.findall(text))
    if len(text) >= MIN_POLICY_CHARS and hits >= 8:
        return True
    return len(text) >= MIN_CONFIRMED_CHARS and hits >= 3 and bool(re.search(r"privacy|data-?policy", urlsplit(url).path, I))


NOT_THE_POLICY = re.compile(r"cookie|choices|do not sell|settings|preferences|center|centre|children|kids|faq|security|terms", I)


def best_link(links, page_url):
    """The likeliest link to this site's privacy policy, or None."""
    here = urlsplit(page_url)
    home = _site_key(here.hostname or "")
    scored = []
    for text, href in links:
        if href.lower().startswith("mailto:"):
            continue
        parts = urlsplit(href)
        if parts.path.rstrip("/") == here.path.rstrip("/") and parts.hostname == here.hostname:
            continue
        label, path = text.lower(), parts.path.lower()
        score = 0
        if re.fullmatch(r"(?:our |global |online )?privacy(?: policy| notice| statement)?", label):
            score = 5
        elif re.search(r"privacy (?:policy|notice|statement)", label):
            score = 4
        elif "privacy" in label:
            score = 2
        if re.search(r"privacy(?:[-_]?(?:policy|notice|statement))?(?:\.\w+)?/?$", path):
            score += 2
        elif "privacy" in path:
            score += 1
        if not score or NOT_THE_POLICY.search(label):
            continue
        scored.append((score + (1 if _site_key(parts.hostname or "") == home else 0), -len(href), href, text))
    if not scored:
        return None
    best = max(scored)
    return best[2], best[3]


def _site_key(host):
    labels = host.lower().removeprefix("www.").split(".")
    if len(labels) >= 3 and labels[-2] in ("co", "com", "org", "net", "ac", "gov", "edu"):
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else labels[0]


def site_name(url):
    """"https://www.walgreens.com/x" -> "Walgreens"."""
    return re.sub(r"(?<=.{3})inc$", "", _site_key(urlsplit(url).hostname or "")).replace("-", " ").title()


def read_policy(url, confirmed=False):
    """{"status": "ok", text, url, site} for a policy page, or {"status": "confirm", url, label, site} when the link was
    a website and we found what looks like its policy. confirmed=True means the reader accepted that page."""
    deadline = time.monotonic() + MAX_SECONDS
    page = download(url, deadline)
    doc = extract(page.html, page.url)
    text = to_text(doc)
    site = site_name(page.url)
    if looks_like_policy(text, page.url) or (confirmed and len(text) >= MIN_CONFIRMED_CHARS):
        return {"status": "ok", "text": text, "url": page.url, "site": site}
    if confirmed:
        raise FetchError(422, f"That page loads its text in a way we can't read. {COPY_IT}")
    found = best_link(doc.links, page.url)
    if found:
        return {"status": "confirm", "url": found[0], "label": found[1], "site": site}
    parts = urlsplit(page.url)
    if re.search(r"privacy|policy|legal", parts.path, I):  # A link to the policy itself: don't guess at another page.
        raise FetchError(422, f"That page loads its text in a way we can't read. {COPY_IT}")
    # The footer may be drawn by scripts: try the usual addresses.
    for path in ("/privacy", "/privacy-policy"):
        guess = f"{parts.scheme}://{parts.hostname}{path}"
        try:
            probe = download(guess, deadline)
        except FetchError:
            continue
        if looks_like_policy(to_text(extract(probe.html, probe.url)), probe.url):
            return {"status": "confirm", "url": probe.url, "label": "Privacy policy", "site": site}
    raise FetchError(422, "We couldn't find a privacy policy on that page. Paste the link to the policy itself, or its text.")
