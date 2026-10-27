import unittest

import numpy as np

from inkwell.common import CATEGORIES
from inkwell.risk import RULES, score_policy
from inkwell.stage1 import analyze, segment


class RiskTests(unittest.TestCase):
    def score(self, text, labels=None):
        segments = segment(text)
        for s in segments:
            s["labels"] = CATEGORIES if labels is None else labels
        return score_policy(segments)

    def test_supported_practices_and_exact_unicode_evidence(self):
        text = ("🔒 We may sell your personal information.\n\n"
                "We share your data with advertising partners.\n\n"
                "We retain personal data indefinitely.\n\n"
                "We don't honor Do-Not-Track signals.\n\n"
                "We may update our privacy policy at any time without prior notice.")
        result = self.score(text)
        self.assertEqual((result["score"], result["max_score"], result["band"]), (100, 100, "high"))
        self.assertEqual(len(result["findings"]), 5)
        for finding in result["findings"]:
            for evidence in finding["evidence"]:
                self.assertEqual(text[evidence["start"]:evidence["end"]], evidence["text"])

    def test_protective_and_neutral_clauses_do_not_add_risk(self):
        text = ("We do not sell your personal information. We never share your data with advertisers. "
                "We do not retain personal data indefinitely. We honor DNT signals. "
                "We will not change this policy without notice. We collect your email address. "
                "We retain your data for 30 days. You may delete your account.")
        result = self.score(text)
        self.assertEqual((result["score"], result["band"], result["findings"]), (0, "no_matches", []))

    def test_category_gate_and_unknown_labels(self):
        for labels in [[], ["Other"], ["Data Security"], ["unknown"]]:
            self.assertEqual(self.score("We sell your personal data.", labels)["score"], 0)
        self.assertEqual(self.score("We sell your personal data.", [RULES[0].category])["score"], 30)

    def test_repetition_cannot_inflate_score(self):
        result = self.score("\n\n".join(["We sell your personal data."] * 20))
        self.assertEqual(result["score"], 30)
        self.assertEqual(len(result["findings"][0]["evidence"]), 20)

    def test_screening_bands(self):
        sale = "We sell your personal data."
        ads = "We share your data with advertisers."
        self.assertEqual(self.score(ads)["band"], "low")
        self.assertEqual(self.score(sale)["band"], "moderate")
        self.assertEqual(self.score(sale + " " + ads)["band"], "high")

    def test_empty_and_unclassified_text_are_not_safe(self):
        for result in [score_policy([]), self.score("Unrelated text", [])]:
            self.assertEqual(result["band"], "no_matches")
            self.assertEqual(len(result["review_gaps"]), 4)
            self.assertIn("not that the policy is safe", result["limitation"])

    def test_mixed_protective_and_adverse_statements_keep_evidence(self):
        result = self.score("We do not sell your data. However, we sell personal data. We honor DNT signals.")
        self.assertEqual(result["score"], 30)
        self.assertEqual(result["findings"][0]["evidence"][0]["text"], "we sell personal data")

    def test_analysis_integration_does_not_use_model_margins_as_risk(self):
        class Fake:
            thresholds = np.zeros(len(CATEGORIES))

            def scores(self, texts):
                return np.ones((len(texts), len(CATEGORIES))) * 100

        result = analyze("We sell your personal data.", Fake())
        self.assertEqual(result["risk"]["score"], 30)
        self.assertEqual(result["coverage"][RULES[0].category], [0])


if __name__ == "__main__":
    unittest.main()
