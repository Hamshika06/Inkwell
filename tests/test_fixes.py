import unittest

from inkwell.fixes import INDUSTRY, KNOWN, classify, fix_links, site_key


class ClassifyTest(unittest.TestCase):
    def test_link_kinds(self):
        cases = {
            ("Do Not Sell or Share My Personal Information", ""): "sale",
            ("Your Privacy Choices", "https://a.example/choices"): "sale",
            ("Delete your account", ""): "delete",
            ("Ad preferences", ""): "ads",
            ("Opt out of interest-based advertising", ""): "ads",
            ("Cookie settings", ""): "cookies",
            ("Submit a privacy request", ""): "rights",
            ("Download your data", ""): "rights",
            ("Privacy settings", ""): "settings",
            ("", "https://a.example/legal/do-not-sell"): "sale",
        }
        for (text, href), kind in cases.items():
            self.assertEqual(classify(text, href), kind, text or href)

    def test_ordinary_links_are_ignored(self):
        for text in ("Home", "Careers", "Terms of Service", "Privacy Policy", "Contact us"):
            self.assertIsNone(classify(text, "https://a.example/x"), text)


class FixLinksTest(unittest.TestCase):
    def test_policy_links_become_fixes(self):
        links = [("Home", "https://a.example/"), ("Cookie settings", "https://a.example/cookies"),
                 ("Do Not Sell My Info", "https://a.example/dns"), ("Email us", "mailto:privacy@a.example")]
        fixes = fix_links(links, "https://a.example/privacy")
        self.assertEqual([(f["kind"], f["url"], f["source"]) for f in fixes],
                         [("cookies", "https://a.example/cookies", "policy"), ("sale", "https://a.example/dns", "policy")])

    def test_known_sites_come_first(self):
        fixes = fix_links([("Delete your account", "https://www.google.com/x")], "https://policies.google.com/privacy")
        self.assertEqual(fixes[0]["source"], "known")
        self.assertIn("delete", [f["kind"] for f in fixes if f["source"] == "known"])

    def test_duplicates_and_limit(self):
        links = [("Cookie settings", "https://a.example/c")] * 3 + [(f"Privacy settings {i}", f"https://a.example/s{i}") for i in range(20)]
        fixes = fix_links(links, "https://a.example/privacy", limit=5)
        self.assertEqual(len(fixes), 5)
        self.assertEqual(sum(f["url"] == "https://a.example/c" for f in fixes), 1)

    def test_same_page_sections_and_vague_text(self):
        links = [("Your privacy controls", "https://a.example/privacy#choices"),
                 ("here", "https://a.example/do-not-sell"), ("Privacy Center", "https://a.example/center/"),
                 ("Privacy Center", "https://a.example/center")]
        fixes = fix_links(links, "https://a.example/privacy")
        self.assertEqual([(f["kind"], f["url"], f.get("text")) for f in fixes],
                         [("sale", "https://a.example/do-not-sell", None), ("settings", "https://a.example/center/", "Privacy Center")])

    def test_site_key(self):
        self.assertEqual(site_key("https://www.google.co.uk/a"), "google")
        self.assertEqual(site_key("https://x.com/privacy"), "x")

    def test_lists_are_https(self):
        for site in KNOWN.values():
            for url in site.values():
                self.assertTrue(url.startswith("https://"), url)
        self.assertTrue(all(i["url"].startswith("https://") for i in INDUSTRY))


if __name__ == "__main__":
    unittest.main()
