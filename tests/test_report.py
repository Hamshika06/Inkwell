import unittest

from inkwell.report import build_report, company_name
from inkwell.stage1 import segment


def report(text):
    return build_report(segment(text))


def sale(text):
    return {c["id"]: c for c in report(text)["checks"]}["sale"]["state"]


class SaleTests(unittest.TestCase):
    def test_polarity(self):
        self.assertEqual(sale("We may sell your personal information to data brokers."), "found")
        self.assertEqual(sale("We do not sell your personal information."), "denied")
        self.assertEqual(sale("Your information will not be sold or rented to anyone."), "denied")
        self.assertEqual(sale("No information will be sold to any other companies or organizations."), "denied")
        self.assertEqual(sale("Our vendors are not authorized to sell your data."), "denied")

    def test_exceptions(self):
        self.assertEqual(sale("We do not sell your data except to our marketing partners."), "found")
        self.assertEqual(sale("We do not sell your data except to our payment processor."), "denied")
        self.assertEqual(sale("We will not sell your information without your express permission."), "consent")
        self.assertEqual(sale("Except as described in this policy, we do not sell your personal information."), "exceptions")

    def test_business_transfers_are_not_sales(self):
        text = "If we are involved in a merger or acquisition, your information may be among the transferred assets."
        self.assertEqual(sale(text), "transfer")
        both = "We do not sell your personal information.\n\n" + text
        self.assertEqual(sale(both), "denied")

    def test_opt_out_link_names_are_not_denials(self):
        self.assertEqual(sale('Click "Do Not Sell My Personal Information" in the footer.'), "missing")

    def test_products_are_not_personal_data(self):
        self.assertEqual(sale("We do not sell products for purchase by children."), "missing")


class PlanTests(unittest.TestCase):
    TEXT = ("Acme Privacy Policy\n\nWe share your information with advertising partners for targeted ads.\n\n"
            "We collect your precise location.\n\nYou can opt out at https://acme.example/choices.\n\n"
            "To delete your data, email privacy@acme.example.")

    def test_concerns_and_steps(self):
        r = report(self.TEXT)
        self.assertEqual(r["company"], "Acme")
        applies = {c["id"]: c["applies"] for c in r["checks"]}
        self.assertEqual((applies["ads"], applies["sharing"], applies["location"], applies["sale"]), (True, True, True, None))
        steps = {s["id"]: s for s in r["steps"]}
        self.assertIn("request_delete", steps)
        self.assertIn("request_optout", steps)  # Ads and sharing apply.
        self.assertEqual(steps["request_delete"]["to"], "privacy@acme.example")
        self.assertEqual(steps["tip_location"]["source"], "general")
        links = [s for s in r["steps"] if s["kind"] == "optout_link"]
        self.assertEqual([s["target"]["value"] for s in links], ["https://acme.example/choices"])
        concerns = {c["id"]: c for c in r["concerns"]}
        self.assertEqual(set(concerns), {"ads", "sharing", "location"})
        self.assertTrue(all(c["fixable"] for c in concerns.values()))
        self.assertIn(links[0]["id"], concerns["ads"]["steps"])

    def test_nothing_to_switch_off(self):
        r = report("We may change this policy at any time without notice.")
        concerns = {c["id"]: c for c in r["concerns"]}
        self.assertEqual(list(concerns), ["changes"])
        self.assertFalse(concerns["changes"]["fixable"])
        self.assertEqual(r["steps"], [])

    def test_company_name(self):
        names = ["Walgreens Online Privacy Policy", "Privacy Notice", "Meta Privacy Policy – How Meta collects",
                 "Pigeonpost Privacy Policy (fictional sample)", "Google's Privacy Policy", None]
        self.assertEqual([company_name(n) for n in names], ["Walgreens", None, "Meta", "Pigeonpost", "Google", None])


if __name__ == "__main__":
    unittest.main()
