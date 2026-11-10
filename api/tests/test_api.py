import time
import unittest
try:
    from fastapi.testclient import TestClient
except ImportError:  # The API is optional for the research pipeline's environment.
    raise unittest.SkipTest("fastapi/httpx not installed; pip install -r api/requirements.txt httpx")
from api.app import MAX_BYTES, MAX_ENCODER_SEGMENTS, MODELS, app
from inkwell.common import CLASSES
from inkwell.stage1 import FAQS


def wait_for_model(client):
    # The model loads in a background thread; the first run also downloads ~500 MB of weights.
    deadline = time.monotonic() + 900
    while "loading" in client.get("/health").json()["models"].values() and time.monotonic() < deadline:
        time.sleep(0.5)
    status = client.get("/models").json()["models"][0]
    if status["status"] != "ready":
        raise AssertionError(f"Model did not load: {status.get('error')}")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, headers={"Origin": "http://localhost:5173"}).__enter__()
        wait_for_model(cls.client)
    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_schema_and_models(self):
        health = self.client.get("/health").json()
        self.assertEqual(health, {"status": "ok", "run": "roberta-five-class-seed42", "models": {"roberta": "ready"}})
        self.assertEqual(self.client.get("/schema").json(), {"categories": CLASSES, "faqs": FAQS})
        self.assertEqual(sorted(FAQS.values()), sorted(CLASSES))  # One common question per topic.
        listing = self.client.get("/models").json()
        self.assertEqual((listing["default"], [m["id"] for m in listing["models"]]), ("roberta", list(MODELS)))
        model = listing["models"][0]
        self.assertEqual((model["status"], model["classes"]), ("ready", CLASSES))
        self.assertAlmostEqual(model["test_macro_f1"], 0.7984, places=4)

    def test_analyze_keeps_demo_contract(self):
        text = "We collect your email address.\n\n  You can request deletion of your data. 🔒"
        response = self.client.post("/analyze", json={"text": text})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        result = response.json()
        self.assertTrue({"text", "segments", "coverage", "faqs", "empty_message"} <= set(result))
        self.assertEqual((result["text"], result["model"]), (text, "roberta"))
        self.assertEqual(list(result["coverage"]), CLASSES)
        self.assertNotIn("risk", result)  # Replaced by the report card.
        self.assertIn("Data Collection & Use", result["segments"][0]["labels"])
        self.assertIn("User Rights & Choices", result["segments"][1]["labels"])
        for s in result["segments"]:
            self.assertEqual(s["text"], text[s["start"]:s["end"]])
            self.assertTrue(all(0 <= x <= 1 for x in s["scores"]))  # Probabilities, like the thresholds.
            # Reported scores must reproduce the labels analyze() assigned.
            passed = [c for c, score, t in zip(CLASSES, s["scores"], result["thresholds"]) if score >= t]
            self.assertEqual(passed, s["labels"])

    def test_model_selection(self):
        for old in ["gpt", "svm", "distilbert"]:  # The ten-category models are no longer served.
            self.assertEqual(self.client.post("/analyze", json={"text": "x", "model": old}).status_code, 400, old)
        self.assertEqual(self.client.post("/analyze", json={"text": "We collect data.", "model": "roberta"}).status_code, 200)
        many = "\n\n".join(["We collect data."] * (MAX_ENCODER_SEGMENTS + 1))
        self.assertEqual(self.client.post("/analyze", json={"text": many}).status_code, 413)

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
        self.assertEqual(self.client.get("/auth-config").json(), {"enabled": False, "guest": False, "firebase": None})
        self.assertIs(self.client.post("/analyze", json={"text": "We collect data."}).json()["guest"], False)

    def test_report_card(self):
        text = ("Acme Privacy Policy\n\nWe do not sell your personal information. We share your information with "
                "advertising partners.\n\nYou can opt out at https://acme.example/choices or email privacy@acme.example.")
        report = self.client.post("/analyze", json={"text": text}).json()["report"]
        checks = {c["id"]: c for c in report["checks"]}
        self.assertEqual(report["title"], "Acme Privacy Policy")
        self.assertEqual((checks["sale"]["state"], checks["sale"]["tone"]), ("denied", "good"))
        self.assertEqual((checks["ads"]["state"], checks["ads"]["tone"]), ("found", "bad"))
        self.assertEqual(checks["retention"]["state"], "missing")
        for check in report["checks"]:
            for e in check["evidence"]:
                self.assertEqual(text[e["start"]:e["end"]], e["text"])
        targets = {t["value"] for a in report["actions"] for t in a["targets"]}
        self.assertEqual(targets, {"https://acme.example/choices", "privacy@acme.example"})


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
        wait_for_model(cls.client)

    def setUp(self):
        self.module._guest_hits.clear()

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
        headers = {} if token is None else {"Authorization": f"Bearer {token}" if token else "Basic abc"}
        return self.client.post("/analyze", json={"text": "We collect your email address."}, headers=headers)

    def test_config_is_public(self):
        config = self.client.get("/auth-config").json()
        self.assertTrue(config["enabled"])
        self.assertEqual(config["firebase"]["projectId"], self.PROJECT)

    def test_valid_token_is_accepted(self):
        self.assertEqual(self.analyze(self.token()).status_code, 200)

    def test_rejected_tokens(self):
        now = int(time.time())
        cases = {"not bearer": "", "other project": self.token(aud="someone-else"),
                 "other issuer": self.token(iss="https://securetoken.google.com/someone-else"),
                 "expired": self.token(iat=now - 7200, exp=now - 3600), "no user": self.token(sub=""),
                 "forged signature": self.token(key=self.other_key), "garbage": "not-a-token"}
        for case, token in cases.items():
            response = self.analyze(token)
            self.assertEqual(response.status_code, 401, case)
            self.assertIn("detail", response.json())

    def test_email_password_accounts_must_be_verified(self):
        password = {"sign_in_provider": "password"}
        self.assertEqual(self.analyze(self.token(firebase=password, email_verified=True)).status_code, 200)
        for case, token in {"unverified": self.token(firebase=password, email_verified=False),
                            "claim missing": self.token(firebase=password)}.items():
            response = self.analyze(token)
            self.assertEqual(response.status_code, 403, case)
            self.assertIn("Confirm your email", response.json()["detail"])

    def test_google_and_github_accounts_skip_the_email_check(self):
        for provider in ["google.com", "github.com"]:
            for verified in [True, False]:
                token = self.token(firebase={"sign_in_provider": provider}, email_verified=verified)
                self.assertEqual(self.analyze(token).status_code, 200, (provider, verified))

    def test_unverified_account_with_a_bad_token_is_still_401(self):
        token = self.token(key=self.other_key, firebase={"sign_in_provider": "password"}, email_verified=False)
        self.assertEqual(self.analyze(token).status_code, 401)

    def test_guests_get_a_limited_free_check(self):
        self.assertTrue(self.client.get("/auth-config").json()["guest"])
        response = self.analyze()
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["guest"], True)
        self.assertIs(self.analyze(self.token()).json()["guest"], False)
        big = self.client.post("/analyze", json={"text": "a" * (self.module.GUEST_MAX_BYTES + 10)})
        self.assertEqual(big.status_code, 413)

    def test_guest_hourly_limit(self):
        for _ in range(self.module.GUEST_PER_HOUR):
            self.assertEqual(self.analyze().status_code, 200)
        self.assertEqual(self.analyze().status_code, 429)
        self.assertEqual(self.analyze(self.token()).status_code, 200)  # Accounts aren't counted.
        other = self.client.post("/analyze", json={"text": "We collect data."}, headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(other.status_code, 200)

    def test_reading_endpoints_stay_open(self):
        for path in ["/health", "/schema", "/models", "/auth-config"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
