import time
import unittest
try:
    from fastapi.testclient import TestClient
except ImportError:  # The API is optional for the research pipeline's environment.
    raise unittest.SkipTest("fastapi/httpx not installed; pip install -r api/requirements.txt httpx")
from api.app import MAX_BYTES, MAX_ENCODER_SEGMENTS, MODELS, app
from inkwell.common import CATEGORIES
from inkwell.stage1 import FAQS

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, headers={"Origin": "http://localhost:5173"}).__enter__()
        deadline = time.monotonic() + 300  # Encoders load in a background thread.
        while "loading" in cls.client.get("/health").json()["models"].values() and time.monotonic() < deadline:
            time.sleep(0.5)
    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_schema_and_models(self):
        health = self.client.get("/health").json()
        self.assertEqual((health["status"], health["run"], health["models"]["svm"]), ("ok", "svm-opp115-seed42", "ready"))
        self.assertEqual(self.client.get("/schema").json(), {"categories": CATEGORIES, "faqs": FAQS})
        models = {m["id"]: m for m in self.client.get("/models").json()["models"]}
        self.assertEqual(set(models), set(MODELS))
        self.assertEqual(models["svm"]["status"], "ready")
        self.assertAlmostEqual(models["roberta"]["test_macro_f1"], 0.7404, places=4)

    def test_analyze_keeps_demo_contract(self):
        text = "We collect your email address.\n\n  You can request deletion of your data. 🔒"
        response = self.client.post("/analyze", json={"text": text})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        result = response.json()
        self.assertTrue({"text", "segments", "coverage", "faqs", "empty_message"} <= set(result))
        self.assertEqual((result["text"], result["model"]), (text, "svm"))
        self.assertEqual(list(result["coverage"]), CATEGORIES)
        for s in result["segments"]:
            self.assertEqual(s["text"], text[s["start"]:s["end"]])
            # Reported scores must reproduce the labels analyze() assigned.
            passed = [c for c, score, t in zip(CATEGORIES, s["scores"], result["thresholds"]) if score >= t]
            self.assertEqual(passed, s["labels"])

    def test_model_selection(self):
        self.assertEqual(self.client.post("/analyze", json={"text": "x", "model": "gpt"}).status_code, 400)
        status = self.client.get("/health").json()["models"]
        for key in ["distilbert", "roberta"]:
            response = self.client.post("/analyze", json={"text": "We collect data.", "model": key})
            self.assertEqual(response.status_code, 200 if status[key] == "ready" else 503, response.text)
            if status[key] == "ready":
                many = "\n\n".join(["We collect data."] * (MAX_ENCODER_SEGMENTS + 1))
                self.assertEqual(self.client.post("/analyze", json={"text": many, "model": key}).status_code, 413)

    def test_rejections(self):
        too_big = self.client.post("/analyze", content=b'{"text":"' + b"a" * MAX_BYTES + b'"}',
                                   headers={"Content-Type": "application/json"})
        self.assertEqual(too_big.status_code, 413)
        for body in ['{"text": ""}', '{"text": "  \\n\\n "}', '{"text": 5}', "{}", "[1]", "not json"]:
            response = self.client.post("/analyze", content=body, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 400, body)

    def test_serves_frontend_without_shadowing_api(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<title>Inkwell", page.text)
        self.assertEqual(self.client.get("/config.js").status_code, 200)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_unlisted_origin_gets_no_cors_header(self):
        response = self.client.get("/health", headers={"Origin": "https://evil.example"})
        self.assertNotIn("access-control-allow-origin", response.headers)

if __name__ == "__main__":
    unittest.main()
