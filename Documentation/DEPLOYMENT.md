# Running and deploying the Inkwell web app

The API in `api/` also serves the frontend in `web/`, so one running service is the whole app: page and API on one URL. The website can also be hosted on its own (Vercel or Firebase Hosting) and call the API on Cloud Run.

Inkwell runs one model: RoBERTa trained on OPP-115, PolicyIE and GoPPC with five classes (`runs/roberta-five-class-seed42`). Its weights (~500 MB) are read from the Hugging Face repo [`Hamshika/inkwell-weights`](https://huggingface.co/Hamshika/inkwell-weights), folder `Five_Class_Combined_Roberta/seed_42` (Step 1). No weights are stored in the project or baked into images.

| Option | What it hosts | Cost | Card needed | Notes |
| --- | --- | --- | --- | --- |
| **Local** (`api\run_local.cmd`) | page + API | free | no | Your machine only |
| **B. Google Cloud Run** | page + API | free within monthly quota | yes (billing account) | 2 GB RAM, scales to zero |
| **Front end on Vercel** | the website only | free (Hobby) | no | Calls the Cloud Run API from B |
| **B+. Firebase Hosting** | the website only | free | no | Calls the Cloud Run API from B |
| **C. Hugging Face Docker Space** | page + API | PRO, $9/month | yes | Docker Spaces now require PRO |

The model can't run on Vercel or on 512 MB free tiers (Render, Koyeb): torch plus RoBERTa needs about 2 GB of memory and a long-running server, and Vercel functions are capped at 250 MB. That's why the API stays on Cloud Run.

**Licensing:** OPP-115 allows research, teaching and scholarship use only, and the five-class model is trained partly on it. Check the PolicyIE and GoPPC licences too before any commercial launch. Keep the weights repo private (Settings → Visibility) and give each deployment an `HF_TOKEN`.

---

## Step 0: Run locally (Windows)

From the repository root, run:

```
api\run_local.cmd     (first run installs torch, ~5 min, then downloads the model, ~500 MB)
```

Then open **http://localhost:7860**. The status light says "Warming up…" until the model has loaded.

What the script does:
- Creates `api\.venv` with **Python 3.10**, using uv, conda or the `py` launcher, whichever exists. The system `python` version does not matter.
- Installs the pinned packages and starts the server.
- Later runs reuse the environment and the downloaded model.

Don't open the HTML files by double-clicking. A page opened as a file can't call the API; the page says so.

**macOS/Linux:** `python3.10 -m venv api/.venv && api/.venv/bin/pip install -r api/requirements-encoders.txt && api/.venv/bin/uvicorn api.app:app --port 7860`.

## Step 1: Model weights (read from Hugging Face)

The model always comes from the Hugging Face model repo `Hamshika/inkwell-weights` (`INKWELL_WEIGHTS_REPO`):

1. When the app starts, it downloads `Five_Class_Combined_Roberta/seed_42/model/` and `.../tokenizer/` (~500 MB). Later starts on the same machine only fetch files that changed.
2. The download goes to a cache **outside the project**: `%USERPROFILE%\.cache\inkwell` on Windows, or the container's own disk in Docker and Cloud Run, where it disappears with the container. Set `INKWELL_WEIGHTS_CACHE` to move it. Nothing is written to `runs/`.
3. The thresholds, labels and test metrics come from `runs/roberta-five-class-seed42/` in git; they match the repo's `seed_42/thresholds.json`.
4. Visitors never download weights. Their browser sends text to the server, and the server runs the model.

Seed 42 is used because it has the best test macro-F1 of the three seeds (7: 0.7979, 13: 0.7945, 42: 0.7984). To switch seeds, change the folder in `REPO_FOLDERS` in `api/app.py` and copy that seed's thresholds and results into the run folder. Never pair one seed's weights with another seed's thresholds.

**Token:** while the weights repo is public no token is needed. Once it's private, put `HF_TOKEN=<read token>` in `.env` at the repository root (git-ignored, never copied into images), and store it as a secret on hosts (Option B shows how).

## Step 2: Sign-in (Firebase Authentication)

The login page (`/login.html`) offers Google, GitHub, and email + username + password, with password reset. Firebase stores the accounts and passwords; Inkwell never sees a password. Until the settings below are present, sign-in is off and the app is open, as before.

1. **Add Firebase to the Google Cloud project.** At https://console.firebase.google.com choose **Create a project → Add Firebase to an existing Google Cloud project** and pick `inkwell-510813`. Analytics is not needed.
2. **Register the web app.** Project settings (gear) → General → Your apps → **Web (`</>`)** → name it "Inkwell web" (no Hosting). Keep the `firebaseConfig` it shows: `apiKey`, `authDomain`, `projectId`, `appId`.
3. **Turn on the sign-in methods.** Build → **Authentication** → Get started → Sign-in method:
   - **Email/Password**: enable (leave "Email link" off).
   - **Google**: enable and choose a support email.
   - **GitHub**: enable. Copy the **callback URL** it shows (`https://inkwell-510813.firebaseapp.com/__/auth/handler`), then on GitHub go to Settings → Developer settings → **OAuth Apps → New OAuth App**. Use homepage `http://localhost:7860` (or the live URL) and paste the callback URL as the **Authorization callback URL**. Register, **Generate a new client secret**, and paste the Client ID and secret back into Firebase.
4. **Authorized domains.** Authentication → Settings → Authorized domains: `localhost` is there by default. Add your live domain (for example `inkwell-846713605562.us-east1.run.app`). Open the app at `http://localhost:7860`, not `127.0.0.1`, unless you add that too.
5. **Give the app the settings.** Add to `.env` at the repository root (these are public client values, not secrets):
   ```
   FIREBASE_API_KEY=<apiKey>
   FIREBASE_AUTH_DOMAIN=inkwell-510813.firebaseapp.com
   FIREBASE_PROJECT_ID=inkwell-510813
   FIREBASE_APP_ID=<appId>
   ```
6. Restart `api\run_local.cmd` and open http://localhost:7860. You are sent to the login page; after signing in you land on the app. The server now rejects analyses without a valid sign-in token (401).
7. **Email confirmation.** Email/password accounts must confirm their address before using the app: they see a "Check your inbox" screen, and the API answers 403 until they do. Google and GitHub accounts skip this. Firebase still creates the account before it is confirmed, so an address that doesn't exist appears under Authentication → Users but can't use the app; delete those now and then. To set the sender name, go to Authentication → Templates → **Email address verification** and edit the template.

On Cloud Run, pass the same four values with `--set-env-vars FIREBASE_API_KEY=...,FIREBASE_AUTH_DOMAIN=...,FIREBASE_PROJECT_ID=...,FIREBASE_APP_ID=...` (alongside `INKWELL_BACKGROUND_LOAD=0`). Users who sign up with the same email through two methods (for example Google and GitHub) are told to use the method they signed up with; Firebase's default is one account per email.

## Step 3: Saved policies (Cloud Firestore)

Signed-in users can save their priorities and checked policies. These go to Cloud Firestore in the Firebase project; until it's set up, the page saves in the browser instead and says so. One-time setup:

1. Firebase console → `inkwell-4a456` → **Build → Firestore Database → Create database**. Choose **Production mode** and a location near your users (for example `nam5` or `us-east1`; it can't be changed later).
2. Deploy the rules from the repository root, so each person can only read and write their own data:
   ```
   firebase deploy --only firestore:rules
   ```
   Or paste `firestore.rules` into **Firestore → Rules** and publish.
3. Nothing changes on Cloud Run or Vercel: the browser talks to Firestore directly with the user's sign-in.

What is stored, per user: `users/{uid}` holds `priorities`; `users/{uid}/policies/{id}` holds the name, optional link, the 8 answers, the choice, ticked steps and a SHA-256 fingerprint of the text. Policy text is never stored. The Spark (free) plan covers a course demo.

## Docker (local)

Start **Docker Desktop** first and wait until it says *Engine running*. `docker info` should print a server version. If it says it can't connect to `dockerDesktopLinuxEngine`, Docker Desktop isn't running. From the repository root:

```sh
docker build -f api/Dockerfile -t inkwell .             # ~1.8 GB image
docker run --rm -p 7860:7860 --env-file .env inkwell    # reads HF_TOKEN and FIREBASE_* from .env
```

Open http://localhost:7860. Use `-p <host-port>:7860`: the right-hand number must stay 7860. The image downloads the model from Hugging Face at startup (under a minute on a fast connection). It runs as a non-root user and listens on `$PORT` (default 7860).

---

## Option B: Google Cloud Run (page + API, free quota, card required)

Cloud Run gives 2 GB containers that scale to zero. The monthly free quota (about 360,000 GiB-seconds) covers a course demo, but you must attach a billing account. Set a budget alert.

1. Create a project at https://console.cloud.google.com and attach billing. In **Billing → Budgets & alerts**, add a $1 budget alert.
2. Install the gcloud CLI (https://cloud.google.com/sdk/docs/install), then:
   ```sh
   gcloud auth login
   gcloud config set project <project-id>
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   ```
3. Store the Hugging Face token as a secret, and let Cloud Run's service account read it (PowerShell):
   ```
   gcloud services enable secretmanager.googleapis.com
   "<your HF read token>" | gcloud secrets create hf-token --data-file=-
   $num = gcloud projects describe <project-id> --format="value(projectNumber)"
   gcloud secrets add-iam-policy-binding hf-token --member="serviceAccount:$num-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
   ```
4. Deploy. Either let Google build from source:
   ```
   api\.venv\Scripts\python -m api.bundle --out dist/deploy
   gcloud run deploy inkwell --source dist/deploy --region us-east1 --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 --set-env-vars INKWELL_BACKGROUND_LOAD=0 --set-secrets HF_TOKEN=hf-token:latest --allow-unauthenticated
   ```
   or push the image you built locally to Artifact Registry and deploy that:
   ```
   gcloud auth configure-docker us-east1-docker.pkg.dev
   docker tag inkwell us-east1-docker.pkg.dev/<project-id>/<repo>/inkwell:latest
   docker push us-east1-docker.pkg.dev/<project-id>/<repo>/inkwell:latest
   gcloud run deploy inkwell --image us-east1-docker.pkg.dev/<project-id>/<repo>/inkwell:latest --region us-east1 --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 --set-env-vars INKWELL_BACKGROUND_LOAD=0 --set-secrets HF_TOKEN=hf-token:latest --allow-unauthenticated
   ```
   - `INKWELL_BACKGROUND_LOAD=0` loads the model before the container accepts traffic. Cloud Run only gives the container CPU during requests, so a background load would stall.
   - `--max-instances 1` caps the cost. 2 GiB covers the model in memory plus its downloaded files (Cloud Run's disk counts against memory).
   - Every check now runs RoBERTa, so CPU sets the speed. `--cpu 4 --memory 4Gi` roughly halves the wait on long policies, but uses the free quota about twice as fast.
5. Open the `https://inkwell-....run.app` URL that the command prints.

Each cold start downloads the model from Hugging Face, so the first visit after idle takes about a minute. RoBERTa takes roughly 0.2–0.5 s per paragraph on CPU, and requests are capped at 200 paragraphs.

## Option B+: Firebase Hosting for the website, Cloud Run for the model

Firebase Hosting serves only static files, so it hosts `web/` at `https://<firebase-project>.web.app` while the Cloud Run service from Option B runs the model. `web/config.js` sends API calls from `*.web.app` / `*.firebaseapp.com` to that Cloud Run URL. Hosting cannot forward to Cloud Run in a different Google Cloud project, so the page calls Cloud Run directly (cross-origin).

1. **Cloud Run settings.** Create `cloudrun-env.yaml` in the repository root (git-ignored) with your Firebase values from `.env`:
   ```yaml
   INKWELL_BACKGROUND_LOAD: "0"
   ALLOWED_ORIGINS: "https://inkwell-4a456.web.app,https://inkwell-4a456.firebaseapp.com"
   FIREBASE_API_KEY: "<FIREBASE_API_KEY>"
   FIREBASE_AUTH_DOMAIN: "inkwell-4a456.firebaseapp.com"
   FIREBASE_PROJECT_ID: "inkwell-4a456"
   FIREBASE_APP_ID: "<FIREBASE_APP_ID>"
   ```
2. **Rebuild and redeploy Cloud Run** with the current code:
   ```
   docker build -f api/Dockerfile -t inkwell .
   docker tag inkwell us-east1-docker.pkg.dev/inkwell-510813/inkwell-repo/inkwell:latest
   docker push us-east1-docker.pkg.dev/inkwell-510813/inkwell-repo/inkwell:latest
   gcloud run deploy inkwell --image us-east1-docker.pkg.dev/inkwell-510813/inkwell-repo/inkwell:latest --region us-east1 --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 --env-vars-file cloudrun-env.yaml --set-secrets HF_TOKEN=hf-token:latest --allow-unauthenticated
   ```
3. **Deploy the website** (`firebase.json` publishes `web/`; `.firebaserc` selects `inkwell-4a456`):
   ```
   npm install -g firebase-tools
   firebase login
   firebase deploy --only hosting
   ```
4. Open `https://inkwell-4a456.web.app`. Firebase authorizes its own `web.app` and `firebaseapp.com` domains for sign-in automatically.

Website-only changes need just `firebase deploy --only hosting`; API or model changes need step 2 again. To serve the site from Firebase and Vercel at once, list both origins in `ALLOWED_ORIGINS`, separated by commas.

## Option C: Hugging Face Docker Space (page + API, PRO required)

Hugging Face now requires PRO ($9/month) to create Docker or Gradio Spaces. If you have PRO:

1. The weights repo already exists (`Hamshika/inkwell-weights`, Step 1). Model repos are still free; only Spaces compute changed.
2. Create a Docker Space (CPU basic) and add the secret `HF_TOKEN` (a read token) under **Settings → Variables and secrets**.
3. Bundle and upload. The bundle's `README.md` carries the Space's YAML header.
   ```sh
   python -m api.bundle --out dist/deploy
   hf upload <hf-user>/inkwell-api dist/deploy . --repo-type space
   ```

## Front end on Vercel (website only; the model stays on Cloud Run)

Vercel hosts the static `web/` folder; every check still goes to the Cloud Run service from Option B. `web/config.js` sends API calls from any `*.vercel.app` address to Cloud Run, and `web/vercel.json` sets the same headers as Firebase Hosting. There is no build step.

**1. Put the code on your fork.** Your local clone's `origin` is the team repo. Add your fork as a second remote and push the branch there:

```
git remote add fork https://github.com/<your-github-user>/Inkwell.git
git push fork web-app
```

Later pushes: `git push fork web-app`. To pick up teammates' changes first: `git pull origin web-app`, then push to `fork`. If your fork is older than the branch, that's fine: pushing `web-app` brings it up to date.

**2. Import it on Vercel.**
1. Sign in at https://vercel.com with GitHub. If Vercel can't see the fork, use **Adjust GitHub App Permissions** and give it access to `<your-github-user>/Inkwell`.
2. **Add New → Project**, then **Import** your fork.
3. Set:
   - **Framework Preset:** Other
   - **Root Directory:** `web` (click **Edit**). This is what makes Vercel serve the site and ignore the Python code.
   - **Build and Output Settings:** leave the build command and output directory empty.
   - **Environment Variables:** none. The site has no secrets; the Firebase settings come from the API.
4. **Deploy.** You get `https://<project-name>.vercel.app`.
5. Vercel's production branch is the fork's default branch (`main`). To deploy `web-app` as production, go to **Settings → Environments → Production → Branch Tracking** and set it to `web-app`. Otherwise every `web-app` push gets a preview URL, and production comes from `main`.

**3. Let that address use the API and sign-in.** Use the exact production URL from step 2, with no trailing slash:

1. **Cloud Run CORS.** Add the Vercel URL to `ALLOWED_ORIGINS` in `cloudrun-env.yaml`, keeping the existing entries:
   ```yaml
   ALLOWED_ORIGINS: "https://inkwell-4a456.web.app,https://inkwell-4a456.firebaseapp.com,https://<project-name>.vercel.app"
   ```
   Then apply it. Rebuild and redeploy if the API code changed (Option B+ step 2); for only this setting:
   ```
   gcloud run services update inkwell --region us-east1 --env-vars-file cloudrun-env.yaml
   ```
2. **Firebase sign-in.** Firebase console → `inkwell-4a456` → **Authentication → Settings → Authorized domains → Add domain** → `<project-name>.vercel.app` (no `https://`).
3. **GitHub sign-in** needs nothing new: its callback is the `firebaseapp.com` handler, which is already registered.

**4. Check it.** Open `https://<project-name>.vercel.app`: the home page loads; **Check a policy free** runs a check (the first one after idle waits for Cloud Run to wake); **Sign in** works with Google, GitHub and email.

Notes:
- **Preview deployments** (random `*-git-*.vercel.app` URLs) load the pages, but checks and sign-in fail there unless you add each address to `ALLOWED_ORIGINS` and Firebase. Test on the production URL.
- **Custom domain:** add it in Vercel (**Settings → Domains**), then add it to `STATIC_HOSTS` in `web/config.js`, to `ALLOWED_ORIGINS` and to Firebase's authorized domains.
- Website-only changes deploy on `git push fork web-app`. API or model changes still need a Cloud Run redeploy.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `pip` tries to compile numpy, or install fails | Wrong Python version. Use `api\run_local.cmd`, which uses 3.10. |
| "running scripts is disabled on this system" | Use `api\run_local.cmd`, which bypasses the policy for this script only. |
| Page says "Opened as a file" | Open http://localhost:7860 instead of the HTML file. |
| `docker` can't connect to `dockerDesktopLinuxEngine` | Start Docker Desktop and wait for *Engine running*. |
| Status light stays "Warming up…" | The model is still downloading or loading. If it turns to "Unavailable", the reason is under "How Inkwell reads a policy" and at `/models` (no network to Hugging Face, a missing `HF_TOKEN` for a private repo, or packages not installed). |
| Vercel site: "Can't reach the Inkwell server" | The Vercel address isn't in Cloud Run's `ALLOWED_ORIGINS` (the browser blocks the call), or Cloud Run is waking up. Check the browser console for a CORS error. |
| Vercel shows a 404 or the repo's README | Root Directory isn't `web`. Fix it in **Settings → Build and Deployment** and redeploy. |
| Login page: "This site's address isn't authorized for sign-in" | Add the domain under Firebase → Authentication → Settings → Authorized domains, or open the app at `http://localhost:7860` |
| Login page: "This sign-in method isn't enabled yet" | Enable that provider in Firebase → Authentication → Sign-in method |
| Login page: "Sign-in isn't set up on this server yet" | The `FIREBASE_*` settings are missing from `.env` (locally) or the service's environment variables |
| Confirmation email doesn't arrive | Check spam, then use "Resend email". Firebase limits how many it sends, so wait a few minutes if it says too many attempts |
| Cloud Run: out of memory | Use `--memory 2Gi` or more. torch plus the model needs about 2 GB. |
| 413 "reads at most 200 paragraphs" | Split the policy, or raise `MAX_ENCODER_SEGMENTS` (each paragraph costs CPU time). |
