import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from inkwell.sale import SalePredictor, multilabel_metrics, targets
from scripts.sale_review import SCHEMA, digest
from scripts.evaluate_sale_baseline import evaluate_test
from scripts.audit_sale_regex import audit_regex
from scripts.train_sale_baseline import evaluation, load_training_data, train_run


def row(identifier, text, split, labels):
    practices = [{"practice_type": practice, "label": polarity,
                  "evidence": [{"start": 0, "end": len(text), "text": text}],
                  "scope": [], "conditions": [], "exceptions": [], "opt_outs": [], "notes": ""}
                 for practice, polarity in labels]
    return {"id": identifier, "doc_id": identifier, "group_id": identifier, "split": split,
            "text": text, "source_labels": [],
            "review": {"sale_related": bool(practices), "practices": practices,
                       "reviewer": "fixture-author", "adjudicator": "", "notes": "Fixture judgment"}}


class SaleBaselineTests(unittest.TestCase):
    def fixture(self, folder):
        train = [row("a", "We sell your personal information.", "train", [("sale", "permitted")]),
                 row("b", "We do not sell your personal data.", "train", [("sale", "denied")]),
                 row("c", "We sell products only.", "train", [])]
        validation = [row("d", "We sell your personal information to partners. validationonlytoken", "validation", [("sale", "permitted")]),
                      row("e", "We do not sell information about you.", "validation", [("sale", "denied")])]
        train_path, val_path = folder / "train.jsonl", folder / "validation.jsonl"
        train_path.write_text("".join(json.dumps(r) + "\n" for r in train))
        val_path.write_text("".join(json.dumps(r) + "\n" for r in validation))
        originals = {r["id"]: copy.deepcopy(r) for r in train + validation}
        (folder / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in originals.values()))
        return train, validation, train_path, val_path, originals

    def test_targets_preserve_opposing_labels_and_collapse_repetition(self):
        pairs = [("sale", "permitted"), ("sale", "denied"), ("business_transfer", "permitted")]
        rows = [row("a", "Scoped statements", "train", [pairs[0], pairs[1], pairs[0]]),
                row("b", "No sale practice", "train", [])]
        np.testing.assert_array_equal(targets(rows, pairs), [[1, 1, 0], [0, 0, 0]])

    def test_absent_class_and_train_only_vocabulary(self):
        pairs = [("sale", "permitted"), ("sale", "unclear")]
        model = SalePredictor(pairs).fit(["We sell data", "We never sell data"], np.array([[1, 0], [0, 0]]))
        guesses = model.predict(["validationonlytoken we sell data"])
        self.assertNotIn("validationonlytoken", model.vectorizer.vocabulary_)
        self.assertEqual(guesses[0, 1], 0)
        self.assertEqual(model.predict([]).shape, (0, 2))

    def test_metrics_report_false_accusations_and_undefined_recall(self):
        pairs = [("sale", "permitted"), ("sale", "denied"), ("sale", "unclear"), ("business_transfer", "conditional")]
        y = np.array([[0, 1, 0, 0], [0, 0, 0, 1], [1, 0, 0, 0]])
        predicted = np.array([[1, 0, 0, 0], [0, 0, 0, 1], [1, 0, 0, 0]])
        result = evaluation(y, predicted, pairs)
        self.assertEqual(result["sale_flag"]["false_positive_rate"], .5)
        self.assertEqual(result["joint"]["per_label"]["sale/permitted"]["confusion_matrix"], [[1, 1], [0, 1]])
        self.assertIsNone(result["joint"]["per_label"]["sale/unclear"]["recall"])
        empty = multilabel_metrics(np.empty((0, 1)), np.empty((0, 1)), ["sale"])
        self.assertIsNone(empty["exact_match"])

    def test_training_serialization_and_fixed_validation_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            train, val, tp, vp, originals = self.fixture(folder)
            with patch("scripts.train_sale_baseline.load_batch", return_value=({}, originals)):
                metadata, metrics = train_run(folder, tp, vp, folder / "run")
                with self.assertRaisesRegex(ValueError, "Run exists"):
                    train_run(folder, tp, vp, folder / "run")
            model = SalePredictor.load(folder / "run/model.joblib")
            predictions = [json.loads(l) for l in (folder / "run/validation_predictions.jsonl").read_text().splitlines()]
            inferred = model.predict([r["text"] for r in val])
            for i, record in enumerate(predictions):
                self.assertEqual(record["predicted_pairs"], [list(p) for p, yes in zip(model.pairs, inferred[i]) if yes])
            self.assertNotIn("validationonlytoken", model.vectorizer.vocabulary_)
            self.assertFalse(metadata["test_evaluation_performed"])
            self.assertEqual(metrics["joint"]["records"], 2)
            self.assertTrue((folder / "run/REPORT.md").exists())

    def test_split_and_group_leakage_rejected(self):
        schema = json.loads(SCHEMA.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            train, val, tp, vp, originals = self.fixture(folder)
            val[0]["group_id"] = train[0]["group_id"]
            originals[val[0]["id"]] = copy.deepcopy(val[0])
            vp.write_text("".join(json.dumps(r) + "\n" for r in val))
            with patch("scripts.train_sale_baseline.load_batch", return_value=({}, originals)):
                with self.assertRaisesRegex(ValueError, "group_id"):
                    load_training_data(folder, tp, vp, schema)
            val[0]["split"] = "test"
            vp.write_text("".join(json.dumps(r) + "\n" for r in val))
            with patch("scripts.train_sale_baseline.load_batch", return_value=({}, originals)):
                with self.assertRaisesRegex(ValueError, "only validation"):
                    load_training_data(folder, tp, vp, schema)

    def test_frozen_test_evaluation_and_declared_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            train, validation, tp, vp, originals = self.fixture(folder)
            test_rows = [row("f", "We may sell your personal data.", "test", [("sale", "permitted")]),
                         row("g", "We never sell customer information.", "test", [("sale", "denied")]),
                         row("h", "We sell products.", "test", [])]
            for item in test_rows:
                item["source_labels"] = ["Third Party Sharing/Collection"]
            originals.update({r["id"]: copy.deepcopy(r) for r in test_rows})
            (folder / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in originals.values()))
            with patch("scripts.train_sale_baseline.load_batch", return_value=({}, originals)):
                train_run(folder, tp, vp, folder / "run")
            model_hash = digest(folder / "run/model.joblib")
            test_path, cohort_path = folder / "test.jsonl", folder / "cohort.json"
            test_path.write_text("".join(json.dumps(r) + "\n" for r in test_rows[:2]))
            cohort = {"version": "fixture-subset", "split": "test", "records": 2,
                      "original_source_records": 3, "selected_ids": ["f", "g"], "excluded_ids": ["h"],
                      "source_candidate_sha256": digest(folder / "candidates.jsonl"),
                      "initial_annotation_sha256": digest(test_path),
                      "selection_reason": "Fixture exclusion declared before inference."}
            cohort_path.write_text(json.dumps(cohort))
            with patch("scripts.evaluate_sale_baseline.load_batch", return_value=({}, originals)), \
                    patch.object(SalePredictor, "fit", side_effect=AssertionError("Test must never fit")):
                run, metrics = evaluate_test(folder / "run", folder, test_path, tp, vp, cohort_path, folder / "test-result")
                self.assertFalse(run["retrained"])
                self.assertFalse(run["threshold_tuning"])
                self.assertEqual(metrics["joint"]["records"], 2)
                predictions_path = folder / "test-result/test_predictions.jsonl"
                predictions = [json.loads(line) for line in predictions_path.read_text().splitlines()]
                self.assertEqual([(r["id"], r["regex_sale_flag"], r["source_category_gated_regex_sale_flag"])
                                  for r in predictions], [("f", True, True), ("g", False, False)])
                report = audit_regex(predictions_path, test_path, folder / "regex-audit")
                self.assertEqual(report["stored_flag_mismatches"], 0)
                self.assertTrue(report["controls_passed"])
                # The audit joins by ID, so record order cannot corrupt the comparison.
                predictions.reverse()
                predictions[0]["regex_sale_flag"] = True
                broken_path = folder / "wrong-flags.jsonl"
                broken_path.write_text("".join(json.dumps(r) + "\n" for r in predictions))
                report = audit_regex(broken_path, test_path, folder / "wrong-flags-audit")
                self.assertEqual(report["stored_flag_mismatches"], 1)
                self.assertEqual(digest(folder / "run/model.joblib"), model_hash)
                with self.assertRaisesRegex(ValueError, "Test result exists"):
                    evaluate_test(folder / "run", folder, test_path, tp, vp, cohort_path, folder / "test-result")
                test_path.write_text("".join(json.dumps(r) + "\n" for r in test_rows))
                with self.assertRaisesRegex(ValueError, "exactly match"):
                    evaluate_test(folder / "run", folder, test_path, tp, vp, cohort_path, folder / "wrong-cohort")
                self.assertFalse((folder / "wrong-cohort").exists())
                # Changed training data must not silently redefine the frozen run.
                tp.write_text(tp.read_text() + "\n")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    evaluate_test(folder / "run", folder, test_path, tp, vp, cohort_path, folder / "changed-input")


if __name__ == "__main__":
    unittest.main()
