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
        self.assertEqual(models["roberta"]["run"], "roberta-c3pa-opp115-seed42")
        self.assertAlmostEqual(models["roberta"]["test_macro_f1"], 0.6688, places=4)

    def test_analyze_keeps_demo_contract(self):
        text = "We collect your email address.\n\n  You can request deletion of your data. 🔒"
        response = self.client.post("/analyze", json={"text": text})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        result = response.json()
        self.assertTrue({"text", "segments", "coverage", "faqs", "empty_message"} <= set(result))
        self.assertEqual((result["text"], result["model"]), (text, "svm"))
        self.assertEqual(list(result["coverage"]), CATEGORIES)
        self.assertEqual(result["risk"]["version"], "1.0.0")
        self.assertEqual(result["risk"]["score"], 0)
        self.assertEqual(result["risk"]["band"], "no_matches")
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

    def test_sign_in_off_without_firebase_settings(self):
        self.assertEqual(self.client.get("/auth-config").json(), {"enabled": False, "firebase": None})


class AuthTests(unittest.TestCase):
    """Sign-in on: a throwaway RSA key stands in for Google's Firebase signing keys."""
    PROJECT = "inkwell-test"

    @classmethod
    def setUpClass(cls):
        import api.app as module
        from cryptography.hazmat.primitives.asymmetric import rsa
        cls.module, cls.saved = module, (module.AUTH_ENABLED, dict(module.FIREBASE), module._jwks)
        cls.key, cls.other_key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
        module.AUTH_ENABLED = True
        module.FIREBASE.update(api_key="test-key", auth_domain="inkwell-test.firebaseapp.com",
                               project_id=cls.PROJECT, app_id="1:2:web:3")
        public = cls.key.public_key()
        module._jwks = type("Keys", (), {"get_signing_key_from_jwt": lambda self, token: type("K", (), {"key": public})()})()
        cls.client = TestClient(app).__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.module.AUTH_ENABLED, firebase, cls.module._jwks = cls.saved
        cls.module.FIREBASE.update(firebase)

    def token(self, key=None, **overrides):
        import jwt
        now = int(time.time())
        claims = {"iss": f"https://securetoken.google.com/{self.PROJECT}", "aud": self.PROJECT, "sub": "user-1",
                  "iat": now, "exp": now + 3600, "auth_time": now, **overrides}
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": "test"})

    def analyze(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/analyze", json={"text": "We collect your email address."}, headers=headers)

    def test_config_is_public(self):
        config = self.client.get("/auth-config").json()
        self.assertTrue(config["enabled"])
        self.assertEqual(config["firebase"]["projectId"], self.PROJECT)

    def test_valid_token_is_accepted(self):
        self.assertEqual(self.analyze(self.token()).status_code, 200)

    def test_rejected_tokens(self):
        now = int(time.time())
        cases = {"missing": None, "other project": self.token(aud="someone-else"),
                 "other issuer": self.token(iss="https://securetoken.google.com/someone-else"),
                 "expired": self.token(iat=now - 7200, exp=now - 3600), "no user": self.token(sub=""),
                 "forged signature": self.token(key=self.other_key), "garbage": "not-a-token"}
        for case, token in cases.items():
            response = self.analyze(token)
            self.assertEqual(response.status_code, 401, case)
            self.assertIn("detail", response.json())

    def test_reading_endpoints_stay_open(self):
        for path in ["/health", "/schema", "/models", "/auth-config"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
