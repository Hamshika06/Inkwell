"""Hosted Stage 1 API: uvicorn api.app:app --port 7860 (run from the repository root)."""
import importlib.util
import json
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import sklearn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from inkwell.common import CATEGORIES, ROOT
from inkwell.predict import Predictor
from inkwell.stage1 import FAQS, analyze, segment

# Local secrets such as HF_TOKEN; never overrides variables a host already set. .env is git-ignored
# and not copied into images.
load_dotenv(ROOT / ".env")

RUNS = ROOT / "runs"
WEB = ROOT / "web"
MODELS = {"svm": ("TF-IDF + SVM", "svm-opp115-seed42"),
          "distilbert": ("DistilBERT", "distilbert-opp115-seed42"),
          "roberta": ("RoBERTa-base", "roberta-opp115-seed42")}
DEFAULT_MODEL = "svm"
MAX_BYTES = 1_000_000  # Same limit as demo/server.py.
# Encoders cost ~0.1-0.25 s per paragraph on CPU; cap them so one request cannot hold the server for minutes.
MAX_ENCODER_SEGMENTS = int(os.environ.get("MAX_ENCODER_SEGMENTS", 200))
ENABLED = [m.strip() for m in os.environ.get("INKWELL_MODELS", ",".join(MODELS)).split(",") if m.strip() in MODELS]
# Encoder weights always come from this Hugging Face model repo (never from the project folder), read
# with HF_TOKEN. It holds <folder>/model/ and <folder>/tokenizer/ per run.
WEIGHTS_REPO = os.environ.get("INKWELL_WEIGHTS_REPO", "Hamshika/inkwell-weights")
# Where downloaded weights are kept while the app runs: outside the repository, reused across restarts on
# the same machine. On Cloud Run and in Docker it is the container's own disk and disappears with it.
WEIGHTS_CACHE = Path(os.environ.get("INKWELL_WEIGHTS_CACHE", Path.home() / ".cache" / "inkwell"))
# Folder names to try in the weights repo, run name first. RoBERTa was uploaded as "robertabert-...".
REPO_FOLDERS = {"roberta-opp115-seed42": ["roberta-opp115-seed42", "robertabert-opp115-seed42"]}
# Load encoders after the server starts (default) or before it accepts traffic ("0"; for hosts such as
# Cloud Run that throttle CPU outside requests, where a background load would stall).
BACKGROUND_LOAD = os.environ.get("INKWELL_BACKGROUND_LOAD", "1") != "0"
ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]


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
    encoder = json.loads((run / "run.json").read_text())["kind"] != "svm"
    if encoder and importlib.util.find_spec("torch") is None:
        raise RuntimeError("Encoder packages are not installed (pip install -r api/requirements-encoders.txt)")
    predictor = Predictor(fetch(run) if encoder else run)
    # model.joblib is a pickle; refuse to serve from a scikit-learn it was not saved with.
    if predictor.run["kind"] == "svm" and predictor.run.get("sklearn") != sklearn.__version__:
        raise RuntimeError(f"{run.name} was saved with scikit-learn {predictor.run.get('sklearn')}, "
                           f"but {sklearn.__version__} is installed")
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
    test = json.loads((RUNS / run_name / "test_metrics.json").read_text())["opp115"]
    return {"id": key, "label": label, "run": run_name, "kind": run["kind"], "status": slot["status"],
            "error": slot.get("error"), "score_type": run["score_type"],
            "test_macro_f1": test["macro_f1"], "test_micro_f1": test["micro_f1"],
            "cpu_ms_per_segment": run["cpu_ms_per_segment"]}


@asynccontextmanager
async def lifespan(app):
    slots = app.state.models = {key: {"status": "loading"} for key in ENABLED}
    if DEFAULT_MODEL in slots:  # The SVM loads in milliseconds; serve it before the encoders finish.
        load_into(slots, [DEFAULT_MODEL])
        if slots[DEFAULT_MODEL]["status"] != "ready":
            raise RuntimeError(slots[DEFAULT_MODEL]["error"])
    rest = [k for k in ENABLED if k != DEFAULT_MODEL]
    if BACKGROUND_LOAD:
        threading.Thread(target=load_into, args=(slots, rest), daemon=True).start()
    else:
        await run_in_threadpool(load_into, slots, rest)
    yield


app = FastAPI(title="Inkwell API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


class Recorder:
    """Passes calls through to a Predictor and keeps the scores analyze() thresholded."""
    def __init__(self, predictor):
        self.predictor, self.thresholds, self.last = predictor, predictor.thresholds, None

    def scores(self, texts):
        self.last = self.predictor.scores(texts)
        return self.last


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "run": MODELS[DEFAULT_MODEL][1],
            "models": {key: slot["status"] for key, slot in request.app.state.models.items()}}


@app.get("/schema")
def schema():
    return {"categories": CATEGORIES, "faqs": FAQS}


@app.get("/models")
def models(request: Request):
    return {"default": DEFAULT_MODEL,
            "models": [describe(key, slot) for key, slot in request.app.state.models.items()]}


@app.post("/analyze")
async def analyze_policy(request: Request):
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(413, "Policy text exceeds the 1 MB limit")
    body = bytearray()
    async for chunk in request.stream():  # Also enforces the limit when Content-Length is absent.
        body += chunk
        if len(body) > MAX_BYTES:
            raise HTTPException(413, "Policy text exceeds the 1 MB limit")
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
        raise HTTPException(503, f"{MODELS[key][0]} is {slot['status']}" + (f": {slot['error']}" if "error" in slot else ""))
    predictor = slot["predictor"]
    if predictor.run["kind"] != "svm" and len(segment(text)) > MAX_ENCODER_SEGMENTS:
        raise HTTPException(413, f"{MODELS[key][0]} accepts at most {MAX_ENCODER_SEGMENTS} paragraphs; "
                                 "use the SVM or submit a shorter policy")
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
    result.update(model=key, run=MODELS[key][1], score_type=predictor.run["score_type"],
                  thresholds=[round(float(t), 4) for t in predictor.thresholds],
                  elapsed_ms=round((time.perf_counter() - start) * 1000, 1))
    return result


# Serve the frontend from the same origin when web/ is present (local runs and single-service deploys).
# Mounted last so the API routes above take precedence.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
