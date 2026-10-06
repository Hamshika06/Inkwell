# All three models + the web frontend. Build from the repository root:
#   docker build -f api/Dockerfile -t inkwell .
# Needs ~2 GB RAM with both encoders loaded. Encoder weights are not baked in: mount them under
# runs/<run>/model and tokenizer, or set INKWELL_WEIGHTS_REPO (+ HF_TOKEN if private) to download at startup.
# For a 512 MB free host, use api/Dockerfile.svm instead.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/home/user/.cache/huggingface
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY api/requirements.txt api/requirements-encoders.txt api/
RUN pip install --no-cache-dir -r api/requirements-encoders.txt

COPY --chown=user inkwell/ inkwell/
COPY --chown=user configs/ configs/
COPY --chown=user runs/svm-opp115-seed42/ runs/svm-opp115-seed42/
COPY --chown=user runs/distilbert-opp115-seed42/ runs/distilbert-opp115-seed42/
COPY --chown=user runs/roberta-opp115-seed42/ runs/roberta-opp115-seed42/
COPY --chown=user api/ api/
COPY --chown=user web/ web/

USER user
EXPOSE 7860
# Hosts such as Render and Cloud Run set $PORT; 7860 otherwise.
CMD ["sh", "-c", "exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
