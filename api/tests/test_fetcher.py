import socket
import time
import unittest
from unittest import mock

from api import fetcher
from api.fetcher import FetchError, best_link, download, extract, looks_like_policy, read_policy, site_name, to_text

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
POLICY_BODY = "".join(f"<p>We collect your personal information and share your data with third parties, section {i}. Cookies are used for privacy reasons.</p>" for i in range(30))


def resolves_to(*ips):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


class SafetyTests(unittest.TestCase):
    def assert_refused(self, url):
        with self.assertRaises(FetchError) as caught:
            download(url, time.monotonic() + 5)
        self.assertEqual(caught.exception.status, 400, url)

    def test_bad_schemes_ports_and_credentials(self):
        for url in ["ftp://example.com/", "file:///etc/passwd", "https://example.com:8080/", "https://user:pw@example.com/", "http://[bad"]:
            self.assert_refused(url)

    def test_private_addresses(self):
        for ip in ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fd00::1", "::ffff:127.0.0.1"]:
            with mock.patch("socket.getaddrinfo", return_value=resolves_to(ip)):
                self.assert_refused("https://sneaky.example/")

    def test_one_private_address_among_public_ones_is_refused(self):
        with mock.patch("socket.getaddrinfo", return_value=resolves_to("93.184.216.34", "10.0.0.5")):
            self.assert_refused("https://sneaky.example/")

    def test_redirect_to_an_internal_address_is_refused(self):
        def lookup(host, *_a, **_k):
            return resolves_to("169.254.169.254" if host == "metadata.google.internal" else "93.184.216.34")
        with mock.patch("socket.getaddrinfo", side_effect=lookup), \
             mock.patch.object(fetcher, "_request", return_value=(302, {"Location": "http://metadata.google.internal/computeMetadata/v1/"}, b"")):
            self.assert_refused("https://example.com/")

    def test_connects_to_the_checked_address(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLIC), \
             mock.patch.object(fetcher, "_request", return_value=(200, {"Content-Type": "text/html"}, b"<p>x</p>")) as sent:
            download("example.com/a b", time.monotonic() + 5)
        self.assertEqual(sent.call_args.args[:5], ("https", "example.com", 443, "93.184.216.34", "/a%20b"))

    def test_unreadable_responses_explain_themselves(self):
        cases = [(403, "text/html", "automated"), (404, "text/html", "doesn't exist"), (200, "application/pdf", "PDF")]
        for status, ctype, phrase in cases:
            with mock.patch("socket.getaddrinfo", return_value=PUBLIC), \
                 mock.patch.object(fetcher, "_request", return_value=(status, {"Content-Type": ctype}, b"")):
                with self.assertRaises(FetchError) as caught:
                    download("https://example.com/", time.monotonic() + 5)
            self.assertEqual(caught.exception.status, 422)
            self.assertIn(phrase, caught.exception.detail)


class ExtractionTests(unittest.TestCase):
    PAGE = """<html><head><title>Acme | Privacy</title><style>p{}</style></head><body>
      <header><a href="/">Home</a> Site menu</header><nav><a href="/shop">Shop</a></nav>
      <div class="cookie-banner">We use cookies, accept?</div>
      <main><h1>Acme Privacy Policy</h1>
        <h2>What we collect</h2><p>We collect your email &amp; name.</p>
        <p>We share data with:</p><ul><li>Advertisers</li><li>Vendors</li></ul>
        <p>You can <a href="/choices">opt out here</a> or write to <a href="mailto:privacy@acme.example">our team</a>.</p>
        <script>alert(1)</script></main>
      <footer><a href="/privacy">Privacy</a> Copyright</footer></body></html>"""

    def test_paragraphs(self):
        text = to_text(extract(self.PAGE, "https://acme.example/privacy"))
        paragraphs = text.split("\n\n")
        self.assertEqual(paragraphs[0], "Acme Privacy Policy")
        self.assertEqual(paragraphs[1], "What we collect\nWe collect your email & name.")
        self.assertEqual(paragraphs[2], "We share data with:\nAdvertisers\nVendors")
        self.assertIn("opt out here (https://acme.example/choices)", paragraphs[3])
        self.assertIn("our team (privacy@acme.example)", paragraphs[3])
        for junk in ["Site menu", "Shop", "accept?", "alert(1)", "Copyright"]:
            self.assertNotIn(junk, text)

    def test_links_in_the_footer_are_still_found(self):
        self.assertIn(("Privacy", "https://acme.example/privacy"), extract(self.PAGE, "https://acme.example/").links)

    def test_stays_under_the_paragraph_limit(self):
        html = "<body>" + "".join(f"<p>Short paragraph number {i} about data.</p>" for i in range(900)) + "</body>"
        self.assertLessEqual(len(to_text(extract(html, "https://a.example/")).split("\n\n")), fetcher.MAX_PARAGRAPHS)

    def test_broken_html_does_not_break_reading(self):
        self.assertIn("Still read", to_text(extract("<div><p>Still read<li>and this<nav>menu", "https://a.example/")))

    def test_recognising_a_policy(self):
        policy = to_text(extract(f"<body>{POLICY_BODY}</body>", "https://a.example/"))
        self.assertTrue(looks_like_policy(policy, "https://a.example/legal"))
        self.assertFalse(looks_like_policy("Welcome to our shop. Buy shoes today. " * 80, "https://a.example/"))

    def test_finding_the_policy_link(self):
        links = [("Cookie policy", "https://a.example/cookies"), ("Do Not Sell", "https://a.example/privacy-choices"),
                 ("Privacy Policy", "https://a.example/legal/privacy"), ("Blog", "https://a.example/blog")]
        self.assertEqual(best_link(links, "https://a.example/"), ("https://a.example/legal/privacy", "Privacy Policy"))
        self.assertIsNone(best_link([("Blog", "https://a.example/blog")], "https://a.example/"))

    def test_site_name(self):
        self.assertEqual([site_name(u) for u in ["https://www.walgreens.com/x", "https://bbc.co.uk/", "https://policies.google.com/privacy"]],
                         ["Walgreens", "Bbc", "Google"])


class FlowTests(unittest.TestCase):
    @staticmethod
    def pages(mapping):
        def fake(url, deadline):
            if url not in mapping:
                raise FetchError(422, "missing")
            return fetcher.Page(url, mapping[url], "text/html")
        return mock.patch.object(fetcher, "download", side_effect=fake)

    def test_policy_page_is_read_directly(self):
        with self.pages({"https://a.example/privacy": f"<body>{POLICY_BODY}</body>"}):
            result = read_policy("https://a.example/privacy")
        self.assertEqual((result["status"], result["site"]), ("ok", "A"))
        self.assertIn("We collect", result["text"])

    def test_homepage_asks_before_using_what_it_found(self):
        home = '<body><p>Welcome to our shop.</p><footer><a href="/privacy">Privacy Policy</a></footer></body>'
        with self.pages({"https://a.example/": home}):
            result = read_policy("https://a.example/")
        self.assertEqual((result["status"], result["url"]), ("confirm", "https://a.example/privacy"))

    def test_common_addresses_are_tried_when_no_link_is_found(self):
        with self.pages({"https://a.example/": "<body><p>Welcome.</p></body>", "https://a.example/privacy-policy": f"<body>{POLICY_BODY}</body>"}):
            self.assertEqual(read_policy("https://a.example/")["status"], "confirm")

    def test_nothing_found_says_what_to_do(self):
        with self.pages({"https://a.example/": "<body><p>Welcome.</p></body>"}):
            with self.assertRaises(FetchError) as caught:
                read_policy("https://a.example/")
        self.assertIn("Paste the link to the policy", caught.exception.detail)

    def test_policy_link_that_needs_scripts_does_not_guess(self):
        with self.pages({"https://a.example/policies/privacy": "<body><main></main></body>", "https://a.example/privacy": f"<body>{POLICY_BODY}</body>"}):
            with self.assertRaises(FetchError) as caught:
                read_policy("https://a.example/policies/privacy")
        self.assertIn("can't read", caught.exception.detail)

    def test_collapsed_sections_of_the_policy_are_read(self):
        html = '<body><div hidden>Menu overlay</div><main><p>Intro</p><div hidden><p>Collapsed section</p></div></main></body>'
        text = to_text(extract(html, "https://a.example/"))
        self.assertIn("Collapsed section", text)
        self.assertNotIn("Menu overlay", text)

    def test_script_only_page_after_confirming(self):
        with self.pages({"https://a.example/privacy": "<body><div id=app></div></body>"}):
            with self.assertRaises(FetchError) as caught:
                read_policy("https://a.example/privacy", confirmed=True)
        self.assertIn("copy the policy text", caught.exception.detail)

    # ---- Smaller sites ----

    def test_policy_inside_an_aside_is_read(self):
        html = f'<body><aside class="sidebar"><p>Side menu</p></aside><main><aside class="text-rich-text w-richtext">{POLICY_BODY}</aside></main></body>'
        text = to_text(extract(html, "https://a.example/privacy-policy"))
        self.assertIn("We collect", text)
        self.assertNotIn("Side menu", text)

    def test_a_home_page_that_talks_about_data_is_not_the_policy(self):
        home = ("<body><main>" + "<p>Your data is safe with us. We protect your personal information and your data with bank-level privacy. "
                "No third-party sharing of your information without consent.</p>" * 6 + '</main><footer><a href="/privacy-policy">Privacy Policy</a></footer></body>')
        with self.pages({"https://a.example/": home}):
            result = read_policy("https://a.example/")
        self.assertEqual((result["status"], result["url"]), ("confirm", "https://a.example/privacy-policy"))

    def test_an_error_page_instead_of_the_policy_is_reported(self):
        def fake(url, deadline):
            return fetcher.Page("https://a.example/Error.htm?ref=1", "<body><p>We'll be right back!</p></body>", "text/html")
        with mock.patch.object(fetcher, "download", side_effect=fake):
            with self.assertRaises(FetchError) as caught:
                read_policy("https://a.example/about/privacy", confirmed=True)
        self.assertIn("automated readers", caught.exception.detail)

    def test_the_main_site_is_tried_for_a_subdomain(self):
        with self.pages({"https://app.a.example/": "<body><div id=root></div></body>", "https://www.a.example/privacy": f"<body>{POLICY_BODY}</body>"}):
            result = read_policy("https://app.a.example/")
        self.assertEqual((result["status"], result["url"]), ("confirm", "https://www.a.example/privacy"))

    def test_a_confirmed_page_with_no_privacy_wording_is_refused(self):
        with self.pages({"https://a.example/privacy": "<body><main>" + "<p>Choose your country to continue to the right site.</p>" * 12 + "</main></body>"}):
            with self.assertRaises(FetchError):
                read_policy("https://a.example/privacy", confirmed=True)


if __name__ == "__main__":
    unittest.main()
