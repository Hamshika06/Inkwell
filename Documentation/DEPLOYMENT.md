# Running and deploying the Inkwell web app

The API in `api/` also serves the frontend in `web/`, so one running service is the whole app: page and API on one URL, with no CORS setup.

| Option | Models | Cost | Card needed | Notes |
| --- | --- | --- | --- | --- |
| **Local** (`api\run_local.cmd`) | all three* | free | no | Your machine only |
| **A. Render free web service** | SVM | free | no | 512 MB RAM. Sleeps after 15 min idle; about 1 min to wake |
| **B. Google Cloud Run** | all three* | free within monthly quota | yes (billing account) | 2 GB RAM, scales to zero |
| **C. Hugging Face Docker Space** | all three* | PRO, $9/month | yes | Docker Spaces now require PRO; free accounts cannot create them |

\* DistilBERT and RoBERTa need their weights first (Step 1). Until then their cards show *unavailable* and the SVM works alone.

The encoders cannot run on a 512 MB free tier: torch plus both models needs about 2 GB. That is why option A is SVM-only.

**Licensing:** OPP-115 allows research, teaching and scholarship use only. Present the site as a course research demo. Keep encoder weights in private storage, and never in a public image or repo.

---

## Step 0: Run locally (Windows)

From the repository root, run:

```
api\run_local.cmd            (all three models; first run downloads torch, ~5 min)
api\run_local.cmd -SvmOnly   (SVM only, faster install)
```

Then open **http://127.0.0.1:7860**.

What the script does:
- Creates `api\.venv` with **Python 3.10**, using uv, conda or the `py` launcher, whichever exists. The system `python` version does not matter.
- Installs the pinned packages and starts the server.
- Later runs reuse the environment.

Why this replaces the earlier instructions:
- `python` on this machine is 3.14, and numpy 1.26.4 has no Windows package for it, so `pip install` tries to compile numpy and fails.
- The `py -3.11` install has scikit-learn 1.5.1. The API refuses to start on it because `model.joblib` was saved with 1.7.2.

Don't open `web/index.html` by double-clicking. A page opened as a file can't call the API; the page now says so.

**macOS/Linux:** `python3.10 -m venv api/.venv && api/.venv/bin/pip install -r api/requirements-encoders.txt && api/.venv/bin/uvicorn api.app:app --port 7860`. Use `requirements.txt` instead for SVM only.

## Step 1: Recover the DistilBERT and RoBERTa weights (only for the encoders)

Only the SVM model is in git. The encoder run folders hold metrics and thresholds, but `model/` and `tokenizer/` stayed in the Colab session that trained them.

1. Get `runs/distilbert-opp115-seed42/` and `runs/roberta-opp115-seed42/`, including `model/` and `tokenizer/`, from whoever trained them. Copy them into the same paths here; they are git-ignored.
2. Check that they are the checkpoints the committed thresholds were tuned for. This rescores the validation split, never test:
   ```
   api\.venv\Scripts\python -m api.check_weights runs/distilbert-opp115-seed42   # expect MATCH (0.8212)
   api\.venv\Scripts\python -m api.check_weights runs/roberta-opp115-seed42      # expect MATCH (0.8650)
   ```
   On Windows, run this from a clone made with `git clone -c core.autocrlf=false <url>`. Otherwise Git rewrites `data/` and `configs/` with CRLF line endings, and the frozen-benchmark checksum fails.
3. Restart `api\run_local.cmd`. All three cards should say *ready*.

If the weights are lost, retrain on Colab with the commands in `EXPERIMENTS.md`. A retrain gives new thresholds and metrics, so replace the whole run folder and update the reported numbers. Never pair new weights with the old `thresholds.json`.

## Docker (local)

Start **Docker Desktop** first and wait until it says *Engine running*. `docker info` should print a server version. If it says it can't connect to `dockerDesktopLinuxEngine`, Docker Desktop isn't running. From the repository root:

```sh
docker build -f api/Dockerfile.svm -t inkwell-svm .     # SVM only, ~560 MB image, ~90 MB RAM
docker run --rm -p 7860:7860 inkwell-svm

docker build -f api/Dockerfile -t inkwell .             # all three, ~1.8 GB image
docker run --rm -p 7860:7860 -v "%cd%\runs\distilbert-opp115-seed42\model:/home/user/app/runs/distilbert-opp115-seed42/model:ro" ... inkwell
```

Open http://127.0.0.1:7860. Weights are never baked into the image by default. Mount them as shown, one `-v` per `model` and `tokenizer` folder, or set `INKWELL_WEIGHTS_REPO` (see option C). Both images run as a non-root user and listen on `$PORT` (default 7860).

---

## Option A: Render (free, no card, SVM only)

1. **Get the code onto GitHub where Render can see it.** The repo is `github.com/Hamshika06/Inkwell`. Do one of these:
   - Fork it to your own account and push the `web-app` branch to your fork.
   - Have the owner add you as a collaborator and push `web-app` there. Render's GitHub app then needs approval on the owner's account.
2. Sign up at https://render.com with GitHub.
3. Choose **New → Web Service**, select the repository, and set:
   - **Branch:** `web-app`
   - **Language:** Docker
   - **Dockerfile Path:** `./api/Dockerfile.svm`
   - **Docker Build Context Directory:** `.` (repository root)
   - **Instance Type:** Free
   - **Health Check Path** (under Advanced): `/health`
4. Click **Create Web Service**. The first build takes a few minutes.
5. Open `https://<service-name>.onrender.com`.

Every push to the branch redeploys. On the free tier the service sleeps after 15 minutes without traffic; the next visit takes about a minute while it wakes, and the page's lamp shows this. Koyeb's free tier (512 MB, card required) works the same way with `api/Dockerfile.svm`.

## Option B: Google Cloud Run (all three models, free quota, card required)

Cloud Run gives 2 GB containers that scale to zero. The monthly free quota (about 360,000 GiB-seconds) covers a course demo, but you must attach a billing account. Set a budget alert.

1. Create a project at https://console.cloud.google.com and attach billing. In **Billing → Budgets & alerts**, add a $1 budget alert.
2. Install the gcloud CLI (https://cloud.google.com/sdk/docs/install), then:
   ```sh
   gcloud auth login
   gcloud config set project <project-id>
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   ```
3. Bundle the app with the weights from Step 1. The image goes to your project's private Artifact Registry.
   ```sh
   api\.venv\Scripts\python -m api.bundle --out dist/deploy --with-weights
   ```
4. Deploy:
   ```sh
   gcloud run deploy inkwell --source dist/deploy --region us-central1 \
     --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 \
     --set-env-vars INKWELL_BACKGROUND_LOAD=0 --allow-unauthenticated
   ```
   - `INKWELL_BACKGROUND_LOAD=0` loads all models before the container accepts traffic. Cloud Run only gives the container CPU during requests, so a background load would stall.
   - `--max-instances 1` caps the cost.
5. Open the `https://inkwell-....run.app` URL that the command prints.

A cold start loads the baked-in weights in roughly 15–30 s. RoBERTa takes about 0.25 s per paragraph on CPU, and encoder requests are capped at 200 paragraphs.

## Option C: Hugging Face Docker Space (all three models, PRO required)

Hugging Face now requires PRO ($9/month) to create Docker or Gradio Spaces. If you have PRO:

1. Upload the weights to a **private** model repo, keeping the `<run>/model` and `<run>/tokenizer` layout:
   ```sh
   pip install -U huggingface_hub && hf auth login
   hf repo create inkwell-weights --repo-type model --private
   hf upload <hf-user>/inkwell-weights runs/distilbert-opp115-seed42/model     distilbert-opp115-seed42/model
   hf upload <hf-user>/inkwell-weights runs/distilbert-opp115-seed42/tokenizer distilbert-opp115-seed42/tokenizer
   hf upload <hf-user>/inkwell-weights runs/roberta-opp115-seed42/model        roberta-opp115-seed42/model
   hf upload <hf-user>/inkwell-weights runs/roberta-opp115-seed42/tokenizer    roberta-opp115-seed42/tokenizer
   ```
   Model repos are still free; only Spaces compute changed.
2. Create a public Docker Space (CPU basic). Under **Settings → Variables and secrets**, set:
   - Variable `INKWELL_WEIGHTS_REPO` = `<hf-user>/inkwell-weights`
   - Secret `HF_TOKEN` = a read token for that repo
3. Bundle and upload. The bundle's `README.md` carries the Space's YAML header.
   ```sh
   python -m api.bundle --out dist/deploy
   hf upload <hf-user>/inkwell-api dist/deploy . --repo-type space
   ```

## Hosting the frontend separately (optional)

Every option above already serves the page. If you still want the page on Vercel, Netlify or GitHub Pages:
1. Put the API's URL in `web/config.js`.
2. Deploy the `web/` folder as a static site. On Vercel, set Root Directory `web` and Framework Preset Other.
3. Set `ALLOWED_ORIGINS` on the API to that site's exact origin.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `pip` tries to compile numpy, or install fails | Wrong Python version. Use `api\run_local.cmd`, which uses 3.10. |
| "saved with scikit-learn 1.7.2, but X is installed" | The environment isn't the pinned one. Delete `api\.venv` and rerun the script. |
| "running scripts is disabled on this system" | Use `api\run_local.cmd`, which bypasses the policy for this script only. |
| Page says "Opened as a file" | Open http://127.0.0.1:7860 instead of the HTML file. |
| `docker` can't connect to `dockerDesktopLinuxEngine` | Start Docker Desktop and wait for *Engine running*. |
| A model card says *unavailable* | Its reason is shown on the card and at `/models`: no weights, or encoder packages not installed (`-SvmOnly` setup). |
| Render: "Out of memory" | Use `api/Dockerfile.svm`. The full image needs about 2 GB. |
| 413 on an encoder | More than 200 paragraphs. Use the SVM, or raise `MAX_ENCODER_SEGMENTS`. |
