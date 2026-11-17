import unittest

import numpy as np

from inkwell.sale_score import model_triples, sale_verdict

TEXT = "This is a policy paragraph about personal data."


def para(i, *triples, text=TEXT):
    return {"id": i, "text": text, "triples": list(triples)}


class SaleScoreTests(unittest.TestCase):
    def test_permitted_beats_denied_and_keeps_the_conflict(self):
        result = sale_verdict([para(0, ("sale", "first_party", "denied")),
                               para(1, ("sale", "first_party", "permitted"))])
        self.assertEqual((result["verdict"], result["points"]), ("permitted", 50))
        self.assertEqual([e["id"] for e in result["evidence"]], [1])
        self.assertEqual([a["verdict"] for a in result["also_says"]], ["denied"])

    def test_renting_counts_as_selling(self):
        result = sale_verdict([para(0, ("rental", "first_party", "permitted"))])
        self.assertEqual((result["verdict"], result["points"]), ("permitted", 50))

    def test_conditional_scores_25(self):
        result = sale_verdict([para(0, ("sale", "first_party", "conditional"))])
        self.assertEqual((result["verdict"], result["points"]), ("conditional", 25))

    def test_vague_policy_gets_no_points(self):
        result = sale_verdict([para(0, ("sale", "first_party", "unclear"))])
        self.assertEqual((result["verdict"], result["points"]), ("unclear", 0))
        self.assertIn("vague", result["label"])

    def test_silence_is_not_stated_not_denied(self):
        result = sale_verdict([para(0)])
        self.assertEqual((result["verdict"], result["points"]), ("not_stated", 0))
        self.assertIn("doesn't say", result["label"])
        self.assertEqual(sale_verdict([])["verdict"], "not_stated")

    def test_denied_gets_no_points(self):
        result = sale_verdict([para(0, ("sale", "first_party", "denied"))])
        self.assertEqual((result["verdict"], result["points"], result["label"]),
                         ("denied", 0, "Says they don't sell"))

    def test_service_provider_and_business_transfer_are_ignored(self):
        result = sale_verdict([para(0, ("sale", "service_provider", "permitted")),
                               para(1, ("business_transfer", "first_party", "permitted"))])
        self.assertEqual(result["verdict"], "not_stated")

    def test_repetition_does_not_add_points(self):
        result = sale_verdict([para(i, ("sale", "first_party", "permitted")) for i in range(10)])
        self.assertEqual(result["points"], 50)
        self.assertEqual(len(result["evidence"]), 10)

    def test_headings_are_skipped(self):
        result = sale_verdict([para(0, ("sale", "first_party", "permitted"), text="Sale of Data")])
        self.assertEqual(result["verdict"], "not_stated")

    def test_model_triples_reads_predictions_only(self):
        class FakeModel:
            triples = [("sale", "first_party", "permitted"), ("sale", "first_party", "denied")]

            def predict(self, texts):
                return np.array([[1, 0], [0, 0]])

        self.assertEqual(model_triples(FakeModel(), ["a", "b"]),
                         [[("sale", "first_party", "permitted")], []])


if __name__ == "__main__":
    unittest.main()