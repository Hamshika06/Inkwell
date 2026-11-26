# Moving the model weights into Google Cloud Storage

This copies Inkwell's trained model (about 500 MB) from the Hugging Face repo `Hamshika/inkwell-weights` into a Cloud Storage bucket in the same region as the Cloud Run service. Cloud Run can then load the weights in seconds, without downloading from Hugging Face on every start.

Everything runs in **Cloud Shell**, Google's temporary machine in the browser, so the weights never touch anyone's laptop. It takes about 10 minutes.

---

## Before you start

You need:

| What | Why |
|---|---|
| Owner or Editor role on the Google Cloud project | To create the bucket and grant access |
| Read access to `Hamshika/inkwell-weights` on Hugging Face | Only if that repo is private. Ask the owner to add you as a collaborator, or to create a **read-only** token for you |
| The project ID | Shown at the top of the Google Cloud console |

The values used below:

| Name | Value |
|---|---|
| Region | `us-east1` (same as the current Cloud Run service) |
| Bucket | `inkwell-weights-<PROJECT_ID>` (bucket names must be unique worldwide) |
| Service account for Cloud Run | `inkwell-run` |
| Folder in Hugging Face and in the bucket | `Five_Class_Combined_Roberta/seed_42/` |

---

## Step 1: Open Cloud Shell

1. Go to <https://console.cloud.google.com> and pick the Inkwell project.
2. Click the **Activate Cloud Shell** button (`>_`, top right). A terminal opens at the bottom of the page.

## Step 2: Sign in to Hugging Face (private repo only)

Skip this step if the repo is public.

```bash
pip install -U --quiet huggingface_hub
huggingface-cli login
```

Paste the read-only token when asked. It is stored only inside your Cloud Shell. Don't paste it into chats or documents.

## Step 3: Run the copy script

Paste the whole block into Cloud Shell. Change only the first line.

```bash
# ---- Change this one line ----
PROJECT_ID="your-project-id"

# ---- Leave the rest as it is ----
set -euo pipefail
REGION="us-east1"
BUCKET="inkwell-weights-${PROJECT_ID}"
RUN_SA="inkwell-run@${PROJECT_ID}.iam.gserviceaccount.com"
HF_REPO="Hamshika/inkwell-weights"
RUN_DIR="Five_Class_Combined_Roberta/seed_42"
TMP="$(mktemp -d)"

gcloud config set project "$PROJECT_ID"

echo "1/5 Creating the bucket (skipped if it already exists)…"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access

echo "2/5 Creating the Cloud Run service account (skipped if it already exists)…"
gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create inkwell-run --display-name="Inkwell on Cloud Run"

echo "3/5 Letting Cloud Run read the bucket (read-only)…"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUN_SA}" --role="roles/storage.objectViewer" >/dev/null

echo "4/5 Downloading the weights from Hugging Face into Cloud Shell's temporary folder…"
pip install -U --quiet huggingface_hub
huggingface-cli download "$HF_REPO" --include "${RUN_DIR}/model/*" "${RUN_DIR}/tokenizer/*" --local-dir "$TMP"

echo "5/5 Uploading to gs://${BUCKET}/${RUN_DIR}/ …"
gcloud storage cp -r "${TMP}/Five_Class_Combined_Roberta" "gs://${BUCKET}/"

rm -rf "$TMP"
echo "Done. The temporary copy in Cloud Shell has been deleted."
```

If it stops partway, fix the problem it reports and paste the block again. Steps that already finished are skipped.

## Step 4: Check the upload

```bash
gcloud storage ls -r "gs://inkwell-weights-${PROJECT_ID}/Five_Class_Combined_Roberta/seed_42/"
gcloud storage du -s -r "gs://inkwell-weights-${PROJECT_ID}/Five_Class_Combined_Roberta/seed_42/"
```

You should see these files, about 500 MB in total:

```
.../seed_42/model/config.json
.../seed_42/model/model.safetensors        (or pytorch_model.bin)
.../seed_42/tokenizer/tokenizer.json
.../seed_42/tokenizer/vocab.json
.../seed_42/tokenizer/merges.txt
.../seed_42/tokenizer/special_tokens_map.json
.../seed_42/tokenizer/tokenizer_config.json
```

If `model/` or `tokenizer/` is missing, the Hugging Face repo uses a different folder name. Run this to list what's there:

```bash
python3 -c "from huggingface_hub import list_repo_files as f; print('\n'.join(f('Hamshika/inkwell-weights')))"
```

Then change `RUN_DIR` in Step 3 to match, and run it again.

## Step 5: Tell the developer the bucket is ready

Send them **the bucket name and the folder path only** (no tokens):

```
gs://inkwell-weights-<PROJECT_ID>/Five_Class_Combined_Roberta/seed_42/
```

---

## What happens next (for the developer)

1. **Code change, not done yet.** The app currently only downloads weights from Hugging Face. It needs to load from a folder when `INKWELL_WEIGHTS_DIR` is set, and fall back to Hugging Face otherwise. This is a small change of about 15 lines, plus a test.
2. **Deploy with the bucket attached as a read-only folder:**

```bash
gcloud run deploy inkwell \
  --image us-east1-docker.pkg.dev/${PROJECT_ID}/inkwell/app:v1 --region us-east1 \
  --service-account inkwell-run@${PROJECT_ID}.iam.gserviceaccount.com --execution-environment gen2 \
  --add-volume name=weights,type=cloud-storage,bucket=inkwell-weights-${PROJECT_ID},readonly=true \
  --add-volume-mount volume=weights,mount-path=/weights \
  --set-env-vars INKWELL_WEIGHTS_DIR=/weights/Five_Class_Combined_Roberta/seed_42 \
  --cpu 2 --memory 2Gi --cpu-boost --min-instances 1 --max-instances 3 --concurrency 8 --timeout 120
```

Keep passing the Firebase settings the same way as today. Once the app loads from the bucket, `HF_TOKEN` is no longer needed on Cloud Run.

---

## Updating the weights later

If your teammate trains a better model, upload the new run to a **new folder** (for example `seed_42_v2/`) and point `INKWELL_WEIGHTS_DIR` at it. Don't overwrite the old one. That way you can switch back to the old model with one command if the new one does worse.

## Cost

Storing 500 MB costs about **$0.01 a month**. Reading it from Cloud Run in the same region is free.

## Troubleshooting

| Message | Fix |
|---|---|
| `401` or `Repository Not Found` from Hugging Face | The repo is private: do Step 2, or ask the owner for read access |
| `The requested bucket name is not available` | That name is taken. Add a suffix to `BUCKET`, such as `-ink1`, and use the same name everywhere |
| `Permission denied` on `buckets create` or `add-iam-policy-binding` | Your Google account needs the Owner or Editor role on the project |
| `No space left on device` in Cloud Shell | Run `rm -rf /tmp/tmp.*` and try again. Cloud Shell's temporary space is large enough for this model |
| `gcloud storage ls` shows nothing | Check `PROJECT_ID` is right, and that Step 3 printed "Done" |
