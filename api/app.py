"""Hosted Stage 1 API: uvicorn api.app:app --port 7860 (run from the repository root)."""
import importlib.util
import json
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from inkwell.common import CLASSES, ROOT
from inkwell.predict import Predictor
from inkwell.stage1 import FAQS, analyze, segment

# Local secrets such as HF_TOKEN; never overrides variables a host already set. .env is git-ignored
# and not copied into images.
load_dotenv(ROOT / ".env")

RUNS = ROOT / "runs"
WEB = ROOT / "web"
# The product serves one model: RoBERTa trained on OPP-115, PolicyIE and GoPPC with five classes. The older
# ten-category SVM and DistilBERT runs stay in runs/ for the research results but are not served.
MODELS = {"roberta": ("Inkwell RoBERTa (5 topics)", "roberta-five-class-seed42")}
DEFAULT_MODEL = "roberta"
MAX_BYTES = 1_000_000  # Same limit as demo/server.py.
# RoBERTa costs ~0.2 s per paragraph on CPU; cap it so one request cannot hold the server for minutes.
MAX_ENCODER_SEGMENTS = int(os.environ.get("MAX_ENCODER_SEGMENTS", 200))
ENABLED = list(MODELS)
# Encoder weights always come from this Hugging Face model repo (never from the project folder), read
# with HF_TOKEN. It holds <folder>/model/ and <folder>/tokenizer/ per run.
WEIGHTS_REPO = os.environ.get("INKWELL_WEIGHTS_REPO", "Hamshika/inkwell-weights")
# Where downloaded weights are kept while the app runs: outside the repository, reused across restarts on
# the same machine. On Cloud Run and in Docker it is the container's own disk and disappears with it.
WEIGHTS_CACHE = Path(os.environ.get("INKWELL_WEIGHTS_CACHE", Path.home() / ".cache" / "inkwell"))
# Folder names to try in the weights repo, run name first. The five-class run is uploaded there as
# Five_Class_Combined_Roberta/seed_42 (same thresholds as runs/roberta-five-class-seed42).
REPO_FOLDERS = {"roberta-five-class-seed42": ["roberta-five-class-seed42", "Five_Class_Combined_Roberta/seed_42"]}
# Load encoders after the server starts (default) or before it accepts traffic ("0"; for hosts such as
# Cloud Run that throttle CPU outside requests, where a background load would stall).
BACKGROUND_LOAD = os.environ.get("INKWELL_BACKGROUND_LOAD", "1") != "0"
ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# Sign-in through Firebase Authentication (Google, GitHub, email and password). It is on when the web app's
# Firebase settings are set; /analyze then requires "Authorization: Bearer <Firebase ID token>". These are
# public client settings, not secrets. Without them sign-in is off and the app is open, as before.
FIREBASE = {key: os.environ.get(f"FIREBASE_{key.upper()}", "").strip()
            for key in ("api_key", "auth_domain", "project_id", "app_id")}
AUTH_ENABLED = all(FIREBASE[key] for key in ("api_key", "auth_domain", "project_id"))
# Google's public keys for Firebase ID tokens (rotated by Google; PyJWKClient caches them).
FIREBASE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_jwks = None
# Guests (no account) can try Inkwell when sign-in is on: shorter policies and a per-address hourly limit.
# GUEST_ANALYSES_PER_HOUR=0 turns guest access off.
GUEST_PER_HOUR = int(os.environ.get("GUEST_ANALYSES_PER_HOUR", 20))
GUEST_MAX_BYTES = 300_000
_guest_hits, _guest_lock = {}, threading.Lock()


def client_address(request):
    # Cloud Run appends the caller's address to X-Forwarded-For; earlier entries come from the caller.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "?")


def allow_guest(request):
    """Count one guest analysis for this address; False once it has used its hourly allowance."""
    now, address = time.monotonic(), client_address(request)
    with _guest_lock:
        if len(_guest_hits) > 10_000:  # Forget idle addresses so the table can't grow without bound.
            for key in [k for k, v in _guest_hits.items() if not v or now - v[-1] > 3600]:
                del _guest_hits[key]
        hits = [t for t in _guest_hits.get(address, []) if now - t < 3600]
        if len(hits) >= GUEST_PER_HOUR:
            _guest_hits[address] = hits
            return False
        _guest_hits[address] = hits + [now]
        return True


def verify_user(request, guest_ok=False):
    """Return the signed-in user's token claims, or raise 401 (403 for an unconfirmed email address).
    Returns None when sign-in is off, or for a request without a token when guest_ok is set."""
    global _jwks
    if not AUTH_ENABLED:
        return None
    if guest_ok and not request.headers.get("authorization"):
        return None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in to analyze policies", headers={"WWW-Authenticate": "Bearer"})
    if _jwks is None:
        _jwks = jwt.PyJWKClient(FIREBASE_JWKS_URL, cache_keys=True, lifespan=3600)
    project = FIREBASE["project_id"]
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=project, leeway=60,
                            issuer=f"https://securetoken.google.com/{project}",
                            options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Could not reach Google to check your sign-in; try again")
    except (jwt.PyJWKClientError, jwt.InvalidTokenError):
        raise HTTPException(401, "Your sign-in is invalid or has expired; sign in again",
                            headers={"WWW-Authenticate": "Bearer"})
    if not claims.get("sub"):
        raise HTTPException(401, "Your sign-in is invalid; sign in again", headers={"WWW-Authenticate": "Bearer"})
    # Email and password only: Google and GitHub vouch for their own accounts, and GitHub tokens can say unverified.
    if claims.get("firebase", {}).get("sign_in_provider") == "password" and not claims.get("email_verified"):
        raise HTTPException(403, "Confirm your email address to analyze policies")
    return claims


def fetch(run):
    """Mirror the run's model/ and tokenizer/ from WEIGHTS_REPO into WEIGHTS_CACHE and return a folder
    Predictor can load: those weights next to the run's committed metadata (run.json, labels, thresholds)."""
    from huggingface_hub import HfApi, snapshot_download
    if not WEIGHTS_REPO:
        raise FileNotFoundError("INKWELL_WEIGHTS_REPO is empty; encoder weights come from Hugging Face")
    token = os.environ.get("HF_TOKEN", "").strip() or None  # Secrets stored from a shell often end in a newline.
    names = REPO_FOLDERS.get(run.name, [run.name])
    mirror = WEIGHTS_CACHE / WEIGHTS_REPO.replace("/", "--")
    try:
        files = set(HfApi(token=token).list_repo_files(WEIGHTS_REPO))
        name = next((n for n in names if f"{n}/model/config.json" in files), None)
        if name is None:
            raise LookupError(f"{WEIGHTS_REPO} has no {run.name}/model and {run.name}/tokenizer yet")
        # Fetches only files that changed since the last start. local_dir avoids the shared cache's
        # symlinks, which Windows refuses without Developer Mode.
        snapshot_download(WEIGHTS_REPO, allow_patterns=[f"{name}/model/*", f"{name}/tokenizer/*"],
                          local_dir=mirror, token=token)
    except LookupError:
        raise
    except Exception:  # Hub unreachable: reuse an earlier download on this machine if there is one.
        name = next((n for n in names if (mirror / n / "model").is_dir()), None)
        if name is None:
            raise
    folder = mirror / name
    for file in ("run.json", "labels.json", "thresholds.json"):
        shutil.copy(run / file, folder / file)
    return folder


def load(key):
    run = RUNS / MODELS[key][1]
    if importlib.util.find_spec("torch") is None:
        raise RuntimeError("Model packages are not installed (pip install -r api/requirements-encoders.txt)")
    predictor = Predictor(fetch(run))
    if predictor.labels != CLASSES:
        raise RuntimeError(f"{run.name} has classes {predictor.labels}, expected {CLASSES}")
    return predictor


def load_into(slots, keys):
    for key in keys:
        try:
            slots[key] = {"status": "ready", "predictor": load(key)}
        except Exception as error:  # Report why a model is unavailable instead of taking the API down.
            slots[key] = {"status": "unavailable", "error": f"{type(error).__name__}: {error}"}


def describe(key, slot):
    label, run_name = MODELS[key]
    run = json.loads((RUNS / run_name / "run.json").read_text())
    test = json.loads((RUNS / run_name / "test_metrics.json").read_text())
    return {"id": key, "label": label, "run": run_name, "kind": run["kind"], "status": slot["status"],
            "error": slot.get("error"), "score_type": run["score_type"], "classes": CLASSES,
            "test_macro_f1": test["macro_f1"], "test_micro_f1": test["micro_f1"]}


@asynccontextmanager
async def lifespan(app):
    slots = app.state.models = {key: {"status": "loading"} for key in ENABLED}
    # The first start downloads ~500 MB of weights. Meanwhile /health and /models say "loading" and
    # /analyze answers 503, unless INKWELL_BACKGROUND_LOAD=0 holds traffic until the model is ready.
    if BACKGROUND_LOAD:
        threading.Thread(target=load_into, args=(slots, ENABLED), daemon=True).start()
    else:
        await run_in_threadpool(load_into, slots, ENABLED)
    yield


app = FastAPI(title="Inkwell API", lifespan=lifespan)


@app.middleware("http")
async def revalidate_pages(request: Request, call_next):
    """Pages, scripts and styles must be re-checked on every visit (cheap: ETags answer 304). Without this,
    browsers may reuse an old app.js against a new app.html after a deploy, and the page fails to start."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache"
    return response
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Authorization"])


class Recorder:
    """Passes calls through to a Predictor and keeps the scores analyze() thresholded."""
    def __init__(self, predictor):
        self.predictor, self.labels, self.thresholds, self.last = predictor, predictor.labels, predictor.thresholds, None

    def scores(self, texts):
        self.last = self.predictor.scores(texts)
        return self.last


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "run": MODELS[DEFAULT_MODEL][1],
            "models": {key: slot["status"] for key, slot in request.app.state.models.items()}}


@app.get("/schema")
def schema():
    return {"categories": CLASSES, "faqs": FAQS}


@app.get("/auth-config")
def auth_config():
    """Public Firebase web settings for the login page; "enabled" is false when sign-in is not configured."""
    return {"enabled": AUTH_ENABLED, "guest": AUTH_ENABLED and GUEST_PER_HOUR > 0,
            "firebase": {"apiKey": FIREBASE["api_key"], "authDomain": FIREBASE["auth_domain"],
                         "projectId": FIREBASE["project_id"], "appId": FIREBASE["app_id"]} if AUTH_ENABLED else None}


@app.get("/models")
def models(request: Request):
    return {"default": DEFAULT_MODEL,
            "models": [describe(key, slot) for key, slot in request.app.state.models.items()]}


@app.post("/analyze")
async def analyze_policy(request: Request):
    # Before reading the body: bad tokens, and guests over their allowance, stop here.
    claims = await run_in_threadpool(verify_user, request, GUEST_PER_HOUR > 0)
    guest = AUTH_ENABLED and claims is None
    if guest and not allow_guest(request):
        raise HTTPException(429, "You've used this hour's free checks. Create a free account to keep going")
    limit = GUEST_MAX_BYTES if guest else MAX_BYTES
    too_big = ("Free checks take policies up to 300 KB; create a free account for up to 1 MB" if guest
               else "Policy text exceeds the 1 MB limit")
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, too_big)
    body = bytearray()
    async for chunk in request.stream():  # Also enforces the limit when Content-Length is absent.
        body += chunk
        if len(body) > limit:
            raise HTTPException(413, too_big)
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Body must be JSON: {\"text\": \"...\"}")
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        raise HTTPException(400, "Body must be JSON: {\"text\": \"...\"}")
    if not text.strip():
        raise HTTPException(400, "Policy text is empty")
    key = payload.get("model", DEFAULT_MODEL)
    slot = request.app.state.models.get(key)
    if slot is None:
        raise HTTPException(400, f"Unknown model {key!r}; choose one of {', '.join(request.app.state.models)}")
    if slot["status"] != "ready":
        detail = ("Inkwell is still warming up; try again in a minute" if slot["status"] == "loading"
                  else f"{MODELS[key][0]} is {slot['status']}" + (f": {slot['error']}" if "error" in slot else ""))
        raise HTTPException(503, detail)
    predictor = slot["predictor"]
    if len(segment(text)) > MAX_ENCODER_SEGMENTS:
        raise HTTPException(413, f"Inkwell reads at most {MAX_ENCODER_SEGMENTS} paragraphs at a time; "
                                 "submit a shorter policy or split it in two")
    # Submitted text is never logged or written to disk.
    recorder, start = Recorder(predictor), time.perf_counter()
    try:
        result = await run_in_threadpool(analyze, text, recorder)
    except Exception as error:  # Answer with a JSON error (and CORS headers) rather than a bare 500.
        raise HTTPException(500, f"{MODELS[key][0]} failed: {type(error).__name__}")
    if recorder.last is not None:
        for s, scores in zip(result["segments"], recorder.last):
            s["scores"] = [round(float(x), 4) for x in scores]
    # Additive keys only: the demo's text/segments/coverage/faqs/empty_message contract is unchanged.
    result.update(model=key, run=MODELS[key][1], score_type=predictor.run["score_type"], guest=guest,
                  thresholds=[round(float(t), 4) for t in predictor.thresholds],
                  elapsed_ms=round((time.perf_counter() - start) * 1000, 1))
    return result


# Serve the frontend from the same origin when web/ is present (local runs and single-service deploys).
# Mounted last so the API routes above take precedence.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
