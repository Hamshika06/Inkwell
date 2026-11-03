import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from preprocessing.opp115_preprocess import clean_with_map
from scripts.sale_review import digest, export_batch, map_attribute, read_rows, validate_review


class SaleReviewTests(unittest.TestCase):
    def attribute(self, selected="sell", start=6, end=10):
        raw = "We <b>sell</b> your data."
        clean, indices = clean_with_map(raw)
        return raw, clean, indices, {"selectedText": selected, "startIndexInSegment": start,
                                     "endIndexInSegment": end, "value": "Receive/Shared with"}

    def test_remapped_spans_and_original_offsets(self):
        raw, clean, indices, attr = self.attribute()
        result = map_attribute(attr, raw, clean, indices)
        self.assertEqual(result["span_status"], "exact")
        self.assertEqual(result["span"], {"start": 3, "end": 7, "text": "sell"})
        self.assertEqual(result["original"], attr)
        span = result["verified_raw_span"]
        self.assertEqual(raw[span["start"]:span["end"]], span["text"])

    def test_unique_repairs_and_unusable_spans(self):
        raw, clean, indices, attr = self.attribute(start=0, end=4)
        self.assertEqual(map_attribute(attr, raw, clean, indices)["span_status"], "repaired_unique")
        self.assertEqual(map_attribute(attr, raw, clean, indices, True)["span_status"], "known_errant")
        attr["selectedText"] = "missing"
        result = map_attribute(attr, raw, clean, indices)
        self.assertEqual(result["span_status"], "unmatched")
        self.assertIsNone(result["span"])
        raw = "sell and sell"
        clean, indices = clean_with_map(raw)
        attr["selectedText"] = "sell"
        attr["startIndexInSegment"], attr["endIndexInSegment"] = 1, 5
        self.assertEqual(map_attribute(attr, raw, clean, indices)["span_status"], "ambiguous")

    def make_batch(self, folder):
        raw = "We <b>sell</b> your data only with consent."
        clean, _ = clean_with_map(raw)
        xml = ('<categories xmlns="http://www.w3schools.com"><category>'
               '<name>Third Party Sharing/Collection</name><attributes>'
               '<attribute default="Does"><name>Does/Does Not</name><values>'
               '<value><name>Does</name></value><value><name>Does Not</name></value>'
               '</values></attribute></attributes></category></categories>')
        archive, dataset, batch = folder / "source.zip", folder / "frozen.jsonl", folder / "batch"
        attr = self.attribute()[3]
        annotation = ["1", "batch", "reviewer-1", "ignored", "0", "Third Party Sharing/Collection",
                      json.dumps({"Action Third Party": attr}), "", ""]
        import csv
        import io
        stream = io.StringIO()
        csv.writer(stream).writerow(annotation)
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("OPP-115/sanitized_policies/1_example.com.html", raw)
            z.writestr("OPP-115/annotations/1_example.com.csv", stream.getvalue())
            z.writestr("OPP-115/documentation/categories-july30.xml", xml)
        dataset.write_text(json.dumps({"id": "opp115:1#0000", "doc_id": "opp115:1", "group_id": "dom:example.com",
                                       "source": "opp115", "split": "train", "text": clean, "labels": ["Other"]}) + "\n")
        manifest = export_batch(archive, dataset, batch)
        self.assertEqual(manifest["candidate_segments"], 1)  # No category gate.
        self.assertEqual(manifest["third_party_attribute_schema"]["Does/Does Not"]["default"], "Does")
        self.assertEqual(manifest["candidate_sha256"], digest(batch / "candidates.jsonl"))
        self.assertEqual(read_rows(batch / "test.jsonl"), [])
        row = read_rows(batch / "train.jsonl")[0]
        evidence = {"start": 0, "end": len(clean), "text": clean}
        start = clean.index("only")
        condition = {"start": start, "end": len(clean) - 1, "text": clean[start:-1]}
        row["review"] = {"sale_related": True, "reviewer": "human-a", "adjudicator": "human-b", "notes": "",
                         "practices": [{"label": "conditional", "evidence": [evidence], "conditions": [condition], "exceptions": [], "notes": ""}]}
        return batch, row

    def test_export_and_validate_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            batch, row = self.make_batch(folder)
            reviewed = folder / "reviewed.jsonl"
            reviewed.write_text(json.dumps(row) + "\n")
            self.assertEqual(validate_review(batch, reviewed, folder / "accepted.jsonl"), 1)
            with self.assertRaises(FileExistsError):
                validate_review(batch, reviewed, folder / "accepted.jsonl")

    def test_review_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            batch, original = self.make_batch(folder)
            invalids = []
            row = copy.deepcopy(original); row["text"] += "changed"; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["sale_related"] = None; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["adjudicator"] = "human-a"; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["practices"][0]["conditions"] = []; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["practices"][0]["evidence"][0]["end"] = 3; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["practices"][0]["label"] = "unclear"; invalids.append(row)
            row = copy.deepcopy(original); row["review"]["sale_related"] = False; invalids.append(row)
            for index, row in enumerate(invalids):
                with self.subTest(case=index):
                    reviewed = folder / "reviewed.jsonl"
                    reviewed.write_text(json.dumps(row) + "\n")
                    with self.assertRaises(ValueError):
                        validate_review(batch, reviewed, folder / "accepted.jsonl")

    def test_negative_candidate_and_source_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            batch, row = self.make_batch(folder)
            row["review"].update(sale_related=False, practices=[], notes="Product sale, not personal data sale.")
            reviewed = folder / "reviewed.jsonl"
            reviewed.write_text(json.dumps(row) + "\n")
            self.assertEqual(validate_review(batch, reviewed, folder / "accepted.jsonl"), 1)
            with (batch / "candidates.jsonl").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "Candidate source changed"):
                validate_review(batch, reviewed, folder / "other.jsonl")


if __name__ == "__main__":
    unittest.main()
