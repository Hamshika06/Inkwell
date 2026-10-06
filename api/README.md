---
title: Inkwell API
emoji: 🖋️
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: Privacy-policy clause classifier API (SVM, DistilBERT, RoBERTa)
---

# Inkwell API

HTTP API (and web frontend host) for Inkwell's Stage 1 privacy-policy clause classifier. It calls `inkwell.stage1.analyze` and `inkwell.predict.Predictor` directly, so a given model returns exactly what the local demo (`demo/server.py`) would. Three readers:

| `model` | Run | Test macro / micro F1 (OPP-115 v1) | CPU cost |
| --- | --- | --- | --- |
| `svm` (default) | `runs/svm-opp115-seed42` | 0.700 / 0.746 | <1 ms per paragraph |
| `distilbert` | `runs/distilbert-opp115-seed42` | 0.703 / 0.769 | ~110 ms per paragraph |
| `roberta` | `runs/roberta-opp115-seed42` | 0.740 / 0.800 | ~250 ms per paragraph |

Research baseline trained on OPP-115 (research, teaching and scholarship use only). A missing match may be a classifier error. Not legal advice. Submitted text is not logged or stored.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/health` | `{"status": "ok", "run": "svm-opp115-seed42", "models": {"svm": "ready", ...}}` |
| `GET` | `/schema` | `{"categories": [...10 categories...], "faqs": {question: category}}` |
| `GET` | `/models` | Each model's `status` (`ready`, `loading`, `unavailable`), `error`, test F1 and CPU cost |
| `POST` | `/analyze` | `demo/server.py`'s response, plus extra keys (below) |

`POST /analyze` takes `{"text": "<policy text>", "model": "svm"}`. `model` is optional and defaults to `svm`; separate paragraphs with blank lines. The response keeps the demo contract and adds keys:

```json
{
  "text": "<submitted text, unchanged>",
  "segments": [{"id": 0, "start": 0, "end": 30, "text": "...", "labels": ["First Party Collection/Use"],
                "scores": [1.2, -0.8, "...one per category"]}],
  "coverage": {"<each of the 10 categories>": [segment ids]},
  "faqs": {"Can I delete or access my data?": "User Access, Edit and Deletion", "...": "..."},
  "empty_message": "No matching clause detected",
  "model": "svm", "run": "svm-opp115-seed42", "score_type": "SVM decision margin, not probability",
  "thresholds": [-0.35, "...one per category"], "elapsed_ms": 3.1
}
```

A segment carries a label exactly when `scores[i] >= thresholds[i]`. SVM scores are decision margins; encoder scores are logits (sigmoid gives a probability). `start`/`end` are Unicode code-point offsets into `text`.

Errors return `{"detail": "..."}`:
- **400**: empty or whitespace-only text, non-string `text`, a body that is not a JSON object, or an unknown `model`.
- **413**: body over 1 MB (1,000,000 bytes), or more than `MAX_ENCODER_SEGMENTS` paragraphs for an encoder.
- **503**: the model is still loading or unavailable (the message says why).

## Encoder weights

The SVM model is in git. The DistilBERT and RoBERTa weights (~270 MB and ~500 MB) are not; training saved them on Colab only. At startup the API loads the SVM immediately and loads encoders in the background, from either:

1. `runs/<run>/model/` and `runs/<run>/tokenizer/` on disk (git-ignored), or
2. the Hugging Face model repo named by `INKWELL_WEIGHTS_REPO`, laid out as `<run>/model/...` and `<run>/tokenizer/...`.

An encoder with no weights is reported as `unavailable` and the other models keep working.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS origins. Setting it replaces the default. |
| `INKWELL_WEIGHTS_REPO` | unset | HF model repo with encoder weights, e.g. `your-user/inkwell-weights` |
| `HF_TOKEN` | unset | Read token, needed if the weights repo is private. On a Space, add it as a **secret**. |
| `INKWELL_MODELS` | `svm,distilbert,roberta` | Which models to load |
| `MAX_ENCODER_SEGMENTS` | `200` | Paragraph cap per encoder request |
| `INKWELL_BACKGROUND_LOAD` | `1` | `0` loads encoders before accepting traffic (Cloud Run) |
| `PORT` | `7860` | Listen port inside the Docker images |

## Run locally

Windows, from the repository root: `api\run_local.cmd` (add `-SvmOnly` to skip torch). It creates `api\.venv` with Python 3.10, installs the pins and serves the page and API at http://127.0.0.1:7860. Elsewhere: create a Python 3.10 venv, `pip install -r api/requirements-encoders.txt` (or `requirements.txt` for SVM only), then `uvicorn api.app:app --port 7860`.

When `web/` exists the API serves it at `/`, so the page and API share one origin. API routes take precedence over static files.

The scikit-learn, numpy and joblib pins match what saved `model.joblib`; torch and transformers match training. The app refuses to start if the installed scikit-learn differs from the version recorded in the SVM's `run.json`.

Tests (need `httpx` too): `pip install httpx && python -m unittest discover -s api/tests -t .`

## Docker

| File | Contents | Image | RAM |
| --- | --- | --- | --- |
| `api/Dockerfile.svm` | SVM + web, no torch | ~560 MB | ~90 MB, fits 512 MB free tiers |
| `api/Dockerfile` | all three models + web | ~1.8 GB | ~2 GB with both encoders |

```sh
docker build -f api/Dockerfile.svm -t inkwell-svm . && docker run --rm -p 7860:7860 inkwell-svm
```

Build from the repository root. Both images run as non-root UID 1000 and listen on `$PORT` (default 7860). Weights are never baked in by default.

## Deploy

`python -m api.bundle --out dist/deploy [--svm-only | --with-weights]` assembles a folder with `Dockerfile` (and this README, the Hugging Face Space card) at its root, for hosts that build from an uploaded folder. Step-by-step guides for Render (free, SVM), Google Cloud Run (all three) and Hugging Face Spaces (PRO): `Documentation/DEPLOYMENT.md`.
