import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from inkwell.risk_baseline import (ActorMaskedPredictor, aggregate_or, coverage_targets,
                                   evaluate_masked, masked_metrics, target_triples)
from scripts.sale_review import digest
from scripts.train_risk_baseline import SCHEMA, load_development_data, train_run, validate_split
from scripts.evaluate_risk_baseline import evaluate_run


DEFAULT = {"status": "unannotated", "covered_practice_types": [], "practices": [],
           "annotation_origin": None, "author_id": "", "notes": ""}


def record(identifier, text, split, propositions=(), coverage=("sale",), annotated=True):
    practices = [{"practice_type": kind, "actor": actor, "label": polarity,
                  "evidence": [{"start": 0, "end": len(text), "text": text}],
                  "scope": [], "conditions": [], "exceptions": [], "opt_outs": [], "notes": ""}
                 for kind, actor, polarity in propositions]
    review = {"status": "annotated", "covered_practice_types": list(coverage), "practices": practices,
              "annotation_origin": "model_assisted", "author_id": "fixture-author", "notes": "Fixture judgment"}
    if not annotated:
        review = copy.deepcopy(DEFAULT)
    return {"id": identifier, "source": "fixture", "doc_id": identifier, "group_id": identifier,
            "split": split, "text": text, "labels": [], "label_vec": [0] * 5,
            "label_mask": [1] * 5, "meta": {}, "risk_review": review}


class RiskBaselineTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())
        self.triples = target_triples(self.schema)

    def fixture(self, folder):
        train = [record("a", "We may sell personal information.", "train", [("sale", "first_party", "permitted")]),
                 record("b", "We do not sell your data.", "train", [("sale", "first_party", "denied")]),
                 record("c", "Our vendors may not sell personal information.", "train", [("sale", "service_provider", "denied")]),
                 record("d", "We sell products only.", "train"),
                 record("u", "excludedvocabularytoken should never be fitted.", "train", annotated=False)]
        validation = [record("v", "We will sell your data. validationonlytoken", "validation", [("sale", "first_party", "permitted")]),
                      record("w", "Providers are forbidden to sell personal information.", "validation", [("sale", "service_provider", "denied")]),
                      record("z", "unknownvalidationtoken", "validation", annotated=False)]
        originals = {r["id"]: {k: v for k, v in r.items() if k != "risk_review"} for r in train + validation}
        source = folder / "combined_classifier.jsonl"
        source.write_text("".join(json.dumps(r) + "\n" for r in originals.values()))
        (folder / "review_manifest.json").write_text(json.dumps({"source_sha256": digest(source), "default_risk_review": DEFAULT}))
        for name, rows in [("train", train), ("validation", validation)]:
            (folder / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return train, validation, originals

    def test_actor_masks_do_not_turn_vendor_restrictions_into_first_party_denials(self):
        row = record("a", "Vendor resale is forbidden", "train", [("sale", "service_provider", "denied")])
        y, mask = coverage_targets([row], self.triples)
        first = [j for j, t in enumerate(self.triples) if t[:2] == ("sale", "first_party")]
        vendor = self.triples.index(("sale", "service_provider", "denied"))
        self.assertEqual(int(mask[0, first].sum()), 0)
        self.assertEqual(int(y[0, first].sum()), 0)
        self.assertEqual((y[0, vendor], mask[0, vendor]), (1, 1))
        unknown_other_practice = self.triples.index(("rental", "first_party", "denied"))
        self.assertEqual(mask[0, unknown_other_practice], 0)

    def test_unannotated_checked_negative_and_opposing_scope_targets(self):
        both = [("sale", "first_party", "denied"), ("sale", "first_party", "permitted")]
        rows = [record("u", "Unknown", "train", annotated=False),
                record("n", "Product sales", "train"), record("p", "Different scopes", "train", both + both)]
        y, mask = coverage_targets(rows, self.triples)
        self.assertFalse(mask[0].any())
        self.assertFalse(y[1].any())
        sale = [j for j, t in enumerate(self.triples) if t[0] == "sale"]
        self.assertTrue(mask[1, sale].all())
        self.assertEqual(y[2].sum(), 2)

    def test_masked_metrics_ignore_unknown_fp_and_fn(self):
        y = np.array([[1, 0], [0, 0], [0, 0]])
        mask = np.array([[1, 0], [0, 1], [0, 0]])
        predicted = np.ones((3, 2), dtype=int)
        result = masked_metrics(y, predicted, mask, ["one", "two"])
        self.assertEqual(result["known_cells"], 2)
        self.assertEqual(result["unknown_cells"], 4)
        self.assertEqual(result["per_target"]["one"]["fp"], 0)
        self.assertEqual(result["per_target"]["two"]["fp"], 1)
        self.assertAlmostEqual(result["micro_f1"], 2 / 3)
        self.assertEqual(result["masked_exact_match"], .5)
        self.assertIsNone(result["per_target"]["two"]["recall"])
        with self.assertRaisesRegex(ValueError, "Positive target cannot"):
            masked_metrics(np.ones((1, 1), dtype=int), np.ones((1, 1), dtype=int), np.zeros((1, 1), dtype=int), ["x"])

    def test_three_valued_sale_flag_does_not_score_unknown_actor_as_negative(self):
        rows = [record("a", "Vendor restriction", "train", [("sale", "service_provider", "denied")]),
                record("b", "Sale permitted", "train", [("sale", "first_party", "permitted")]),
                record("c", "No sale practice", "train")]
        y, mask = coverage_targets(rows, self.triples)
        result = evaluate_masked(y, y, mask, self.triples)["first_party_sale_flag"]
        target = result["per_target"]["first_party_sale_permitted_or_conditional"]
        self.assertEqual((target["known"], target["unknown"], target["tp"], target["tn"]), (2, 1, 1, 1))
        truth, _, known = aggregate_or(np.array([[1, 0]]), np.array([[1, 0]]), np.array([[1, 0]]), [0, 1])
        self.assertEqual((truth.item(), known.item()), (1, 1))

    def test_column_fit_support_and_unknown_vocabulary_exclusion(self):
        triples = [("sale", "first_party", "permitted"), ("sale", "service_provider", "denied"),
                   ("rental", "first_party", "unclear")]
        texts = ["We sell data", "We never sell data", "Vendor cannot resell data", "excludedvocabularytoken"]
        y = np.array([[1, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 0]])
        mask = np.array([[1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]])
        model = ActorMaskedPredictor(triples).fit(texts, y, mask)
        self.assertNotIn("excludedvocabularytoken", model.vectorizer.vocabulary_)
        self.assertEqual(model.fitted_records, 3)
        self.assertEqual(model.training_support[0], {"known": 2, "positive": 1, "negative": 1, "state": "learned"})
        self.assertEqual(model.training_support[1]["state"], "positive_only")
        self.assertEqual(model.training_support[2]["state"], "unknown")
        self.assertTrue(np.isnan(model.scores(["anything"])[0, 2]))
        self.assertEqual(model.predict(["anything"])[0, 2], 0)
        self.assertEqual(model.predict([]).shape, (0, 3))
        with self.assertRaisesRegex(ValueError, "No known risk targets"):
            ActorMaskedPredictor(triples).fit([texts[0]], np.zeros((1, 3)), np.zeros((1, 3)))

    def test_full_run_serialization_and_no_test_annotation_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            train, validation, _ = self.fixture(folder)
            # No test annotation file exists; a hidden test dependency would fail.
            run, metrics = train_run(folder, folder / "run")
            self.assertEqual((run["train_used"], run["train_excluded_unknown"]), (4, 1))
            self.assertEqual((run["validation_scored"], run["validation_excluded_unknown"]), (2, 1))
            self.assertFalse(run["test_annotations_read"])
            self.assertFalse(run["test_evaluation_performed"])
            model = ActorMaskedPredictor.load(folder / "run/model.joblib")
            self.assertNotIn("excludedvocabularytoken", model.vectorizer.vocabulary_)
            self.assertNotIn("validationonlytoken", model.vectorizer.vocabulary_)
            predictions = [json.loads(l) for l in (folder / "run/validation_predictions.jsonl").read_text().splitlines()]
            guesses = model.predict([r["text"] for r in validation[:2]])
            for i, record_ in enumerate(predictions):
                self.assertEqual(record_["predicted_triples"], [list(t) for t, hit in zip(model.triples, guesses[i]) if hit])
            self.assertTrue(any(s is None for s in predictions[0]["scores"]))
            self.assertEqual(metrics["joint"]["records"], 2)
            with self.assertRaisesRegex(ValueError, "Run exists"):
                train_run(folder, folder / "run")

    def test_source_mutations_and_annotation_errors_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            train, _, originals = self.fixture(folder)
            mutations = []
            bad = copy.deepcopy(train); bad[0]["text"] += "changed"; mutations.append(bad)
            bad = copy.deepcopy(train); bad[0]["risk_review"]["practices"][0]["actor"] = "unknown_role"; mutations.append(bad)
            bad = copy.deepcopy(train); bad[0]["risk_review"]["covered_practice_types"] = []; mutations.append(bad)
            bad = copy.deepcopy(train); bad[-1]["risk_review"]["practices"] = bad[0]["risk_review"]["practices"]; mutations.append(bad)
            bad = copy.deepcopy(train); bad[0]["risk_review"]["practices"][0]["verbs"] = [{"start": 0, "end": 2, "text": "wrong"}]; mutations.append(bad)
            bad = copy.deepcopy(train); bad[0]["risk_review"]["practices"][0]["label"] = "conditional"; mutations.append(bad)
            for i, bad in enumerate(mutations):
                with self.subTest(case=i), self.assertRaises(ValueError):
                    validate_split(bad, originals, "train", self.schema, DEFAULT)
            with self.assertRaisesRegex(ValueError, "source checksum"):
                with (folder / "combined_classifier.jsonl").open("a") as stream:
                    stream.write("\n")
                load_development_data(folder, self.schema)

    def test_unknown_rows_do_not_change_fit_or_predictions(self):
        rows = [record("a", "We sell data", "train", [("sale", "first_party", "permitted")]),
                record("b", "We never sell data", "train", [("sale", "first_party", "denied")])]
        y, mask = coverage_targets(rows, self.triples)
        first = ActorMaskedPredictor(self.triples).fit([r["text"] for r in rows], y, mask)
        rows.append(record("u", "completelydifferent unknownword", "train", annotated=False))
        y, mask = coverage_targets(rows, self.triples)
        second = ActorMaskedPredictor(self.triples).fit([r["text"] for r in rows], y, mask)
        self.assertEqual(first.vectorizer.vocabulary_, second.vectorizer.vocabulary_)
        np.testing.assert_allclose(first.scores(["We sell data"]), second.scores(["We sell data"]), equal_nan=True)

    def test_frozen_masked_test_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _, _, originals = self.fixture(folder)
            test = [record("t", "We are allowed to sell customer data.", "test", [("sale", "first_party", "permitted")]),
                    record("j", "Our service providers cannot sell the information we give them.", "test", [("sale", "service_provider", "denied")]),
                    record("n", "Only products are sold here.", "test"),
                    record("ut", "neverobservedtestterm", "test", annotated=False)]
            originals.update({r["id"]: {k: v for k, v in r.items() if k != "risk_review"} for r in test})
            source = folder / "combined_classifier.jsonl"
            source.write_text("".join(json.dumps(r) + "\n" for r in originals.values()))
            (folder / "review_manifest.json").write_text(json.dumps({"source_sha256": digest(source),
                "default_risk_review": DEFAULT, "previously_evaluated_test_ids": ["t"]}))
            test_path = folder / "test.jsonl"
            test_path.write_text("".join(json.dumps(r) + "\n" for r in test))
            train_run(folder, folder / "run")
            model_hash, run_hash = digest(folder / "run/model.joblib"), digest(folder / "run/run.json")
            from sklearn.feature_extraction.text import TfidfVectorizer
            with patch.object(ActorMaskedPredictor, "fit", side_effect=AssertionError("No test fitting")), \
                    patch.object(TfidfVectorizer, "fit_transform", side_effect=AssertionError("No vocabulary fitting")):
                result, metrics = evaluate_run(folder / "run", folder, folder / "test-result")
            self.assertEqual((result["test_scored"], result["test_excluded_unknown"]), (3, 1))
            self.assertFalse(result["retrained"])
            self.assertFalse(result["threshold_tuning"])
            self.assertEqual(metrics["prior_sale_v1_clause_exposure"]["previously_evaluated_ids"]["joint"]["records"], 1)
            self.assertEqual(metrics["first_party_sale_flag"]["per_target"]["first_party_sale_permitted_or_conditional"]["unknown"], 1)
            self.assertEqual(digest(folder / "run/model.joblib"), model_hash)
            self.assertEqual(digest(folder / "run/run.json"), run_hash)
            records = [json.loads(line) for line in (folder / "test-result/test_predictions.jsonl").read_text().splitlines()]
            self.assertEqual({r["id"] for r in records}, {"t", "j", "n"})
            self.assertNotIn("ut", {r["id"] for r in records})
            self.assertTrue(any(s is None for s in records[0]["scores"]))
            with self.assertRaisesRegex(ValueError, "Evaluation exists"):
                evaluate_run(folder / "run", folder, folder / "test-result")
            test_path.write_text("".join(json.dumps(r) + "\n" for r in test[:-1]))
            with self.assertRaisesRegex(ValueError, "incomplete or unexpected source split IDs"):
                evaluate_run(folder / "run", folder, folder / "missing-record")
            self.assertFalse((folder / "missing-record").exists())
            test_path.write_text("".join(json.dumps(r) + "\n" for r in test))
            (folder / "train.jsonl").write_text((folder / "train.jsonl").read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                evaluate_run(folder / "run", folder, folder / "changed-input")

    def test_test_with_no_known_targets_is_not_scored_as_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _, _, originals = self.fixture(folder)
            test = record("unknown", "Test paragraph with no risk annotations.", "test", annotated=False)
            originals[test["id"]] = {k: v for k, v in test.items() if k != "risk_review"}
            source = folder / "combined_classifier.jsonl"
            source.write_text("".join(json.dumps(r) + "\n" for r in originals.values()))
            (folder / "review_manifest.json").write_text(json.dumps({"source_sha256": digest(source), "default_risk_review": DEFAULT}))
            (folder / "test.jsonl").write_text(json.dumps(test) + "\n")
            train_run(folder, folder / "run")
            with self.assertRaisesRegex(ValueError, "No known test risk targets"):
                evaluate_run(folder / "run", folder, folder / "test-result")
            self.assertFalse((folder / "test-result").exists())


if __name__ == "__main__":
    unittest.main()
