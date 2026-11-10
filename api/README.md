---
title: Inkwell API
emoji: 🖋️
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: Privacy-policy report cards with a five-class RoBERTa model
---

# Inkwell API

HTTP API (and web frontend host) for Inkwell. It splits a policy into paragraphs, sorts each one into five topics with one model, and builds the privacy report card. It calls `inkwell.stage1.analyze` and `inkwell.predict.Predictor` directly.

| `model` | Run | Test macro / micro F1 | Trained on |
| --- | --- | --- | --- |
| `roberta` (the only one) | `runs/roberta-five-class-seed42` | 0.798 / 0.804 | OPP-115, PolicyIE and GoPPC, mapped to five classes (`data/final_combined_fivecls_data`) |

The five topics, from `configs/five_class_mapping.json`: **Data Collection & Use**, **Data Sharing**, **User Rights & Choices**, **Data Security & Retention**, **Policy Scope & Changes**. A paragraph can have several or none.

The older ten-category runs (SVM, DistilBERT, the C3PA + OPP-115 RoBERTa) stay in `runs/` for the research results but are not served. OPP-115 allows research, teaching and scholarship use only. A missing match may be a classifier error. Not legal advice. Submitted text is not logged or stored.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/health` | `{"status": "ok", "run": "roberta-five-class-seed42", "models": {"roberta": "ready"}}` (`loading` while the weights download) |
| `GET` | `/schema` | `{"categories": [...5 topics...], "faqs": {question: topic}}` |
| `GET` | `/models` | The model's `status` (`ready`, `loading`, `unavailable`), `error`, `classes` and test F1 |
| `GET` | `/auth-config` | `{"enabled": bool, "guest": bool, "firebase": {apiKey, authDomain, projectId, appId}}`: public sign-in settings; `guest` says whether free checks without an account are allowed |
| `POST` | `/analyze` | The analysis below. When sign-in is on, send `Authorization: Bearer <Firebase ID token>`; without the header the request is a **free check** (300 KB, `GUEST_ANALYSES_PER_HOUR` per IP address) |

`POST /analyze` takes `{"text": "<policy text>"}`; separate paragraphs with blank lines. `model` is optional and can only be `roberta`. The response:

```json
{
  "text": "<submitted text, unchanged>",
  "segments": [{"id": 0, "start": 0, "end": 30, "text": "...", "labels": ["Data Collection & Use"],
                "scores": [0.99, 0.02, 0.02, 0.02, 0.02]}],
  "coverage": {"<each of the 5 topics>": [segment ids]},
  "faqs": {"What do they collect about me?": "Data Collection & Use", "...": "..."},
  "empty_message": "No matching clause detected",
  "report": {"checks": ["..."], "tally": {}, "actions": ["..."]},
  "model": "roberta", "run": "roberta-five-class-seed42", "score_type": "probability (sigmoid of the logit)",
  "thresholds": [0.23, 0.81, 0.18, 0.46, 0.47], "guest": false, "elapsed_ms": 410.2
}
```

`report` is the privacy report card (`inkwell/report.py`, version 1.1.0):
- `checks`: eight checks, each with `id`, `title`, `state`, `label`, `meaning`, up to three `evidence` sentences with offsets, `counter` sentences that say the opposite, and `applies` (`true`: the practice applies to you; `false`: it doesn't; `null`: the text doesn't settle it). `tone` is kept for older clients; the page no longer colours by it.
- Sale `state` is one of `found`, `denied`, `exceptions` ("except as described in this policy"), `consent` ("only with your permission"), `transfer` (only if the company is sold or merged) or `missing`. Measured with `python -m scripts.eval_report_sale`.
- `concerns`: the practices that apply, each with `fixable` and the ids of the `steps` that switch it off.
- `steps`: opt-out and request links from the policy (`target`), pre-written requests to its privacy address (`template` of `optout`/`delete`/`access`, `to`), and general advice (`source: "general"`).
- `actions` (raw links, emails and settings paths), `title` when the first paragraph is a heading, and `company` guessed from it.

`guest` is true for a free check.

A segment carries a label exactly when `scores[i] >= thresholds[i]`. Scores are sigmoid probabilities, because the thresholds were tuned on probabilities. Paragraphs longer than 512 tokens are read in overlapping windows, and each topic takes its highest window. `start`/`end` are Unicode code-point offsets into `text`.

Errors return `{"detail": "..."}`:
- **400**: empty or whitespace-only text, non-string `text`, a body that is not a JSON object, or an unknown `model`.
- **401**: sign-in is on and the request has an invalid Firebase ID token (expired, wrong project or bad signature).
- **403**: the token is valid, but it belongs to an email and password account whose address isn't confirmed.
- **413**: body over 1 MB (1,000,000 bytes; 300 KB for a free check), or more than `MAX_ENCODER_SEGMENTS` paragraphs.
- **429**: a free check from an address that has used its hourly allowance.
- **503**: the model is still loading or unavailable (the message says why).

## Model weights

No weights are stored in the project. At startup the API downloads `Five_Class_Combined_Roberta/seed_42/model/` and `.../tokenizer/` (~500 MB) from the Hugging Face model repo [`Hamshika/inkwell-weights`](https://huggingface.co/Hamshika/inkwell-weights) into `INKWELL_WEIGHTS_CACHE`, outside the repository (later starts fetch only changed files). It then loads them next to the committed thresholds in `runs/roberta-five-class-seed42`. Seed 42 has the best test macro-F1 of the three seeds (7: 0.7979, 13: 0.7945, 42: 0.7984). `HF_TOKEN` is needed once the weights repo is private.

If the hub is unreachable, the API reuses an earlier download on the same machine; otherwise the model is reported as `unavailable`.

Speed: about 0.2 s per paragraph on a laptop CPU (a 100-paragraph policy in ~20 s); paragraphs are batched by length. Int8 dynamic quantization was measured at 5.7x faster but cost 2.3 points of macro-F1 on a 400-row test sample, so it is not used.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS origins. Setting it replaces the default. |
| `INKWELL_WEIGHTS_REPO` | `Hamshika/inkwell-weights` | HF model repo with the weights |
| `INKWELL_WEIGHTS_CACHE` | `~/.cache/inkwell` | Where downloaded weights are kept while the app runs |
| `HF_TOKEN` | unset | Read token for the weights repo. Locally put it in the git-ignored `.env`; on a host, store it as a **secret**. |
| `MAX_ENCODER_SEGMENTS` | `200` | Paragraph cap per request |
| `GUEST_ANALYSES_PER_HOUR` | `20` | Free checks (no account) per IP address per hour when sign-in is on. `0` turns free checks off and requires sign-in again. Counted in memory per instance. |
| `INKWELL_BACKGROUND_LOAD` | `1` | `0` loads the model before accepting traffic (Cloud Run) |
| `PORT` | `7860` | Listen port inside the Docker images |
| `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` | unset | Firebase web app settings. When the first three are set, sign-in is on and `/analyze` requires a signed-in user; tokens are checked against Google's public keys. Public values, not secrets. Setup: `Documentation/DEPLOYMENT.md`, "Sign-in". |

## Run locally

Windows, from the repository root: `api\run_local.cmd`. It creates `api\.venv` with Python 3.10, installs the pins and serves the page and API at http://localhost:7860. The first start downloads the model (~500 MB); the page's status light shows "Warming up" until it's ready. Elsewhere: create a Python 3.10 venv, `pip install -r api/requirements-encoders.txt`, then `uvicorn api.app:app --port 7860`.

When `web/` exists the API serves it at `/`, so the page and API share one origin. API routes take precedence over static files.

torch matches training. The weights were saved with transformers 5.x and load with the pinned 4.57 (checked: identical scores).

Tests (need `httpx` too): `pip install httpx && python -m unittest discover -s api/tests -t .`

## Docker

`api/Dockerfile`: the five-class RoBERTa + web, ~1.8 GB image, needs about 2 GB of RAM.

```sh
docker build -f api/Dockerfile -t inkwell . && docker run --rm -p 7860:7860 --env-file .env inkwell
```

Build from the repository root. The image runs as non-root UID 1000 and listens on `$PORT` (default 7860). Weights are never baked in.

## Deploy

`python -m api.bundle --out dist/deploy` assembles a folder with `Dockerfile` (and this README, the Hugging Face Space card) at its root, for hosts that build from an uploaded folder. Step-by-step guides for Google Cloud Run and for hosting the web pages on Vercel: `Documentation/DEPLOYMENT.md`.
