# The five-class RoBERTa API + the web frontend. Build from the repository root:
#   docker build -f api/Dockerfile -t inkwell .
# Weights are not in the image: at startup the app downloads Five_Class_Combined_Roberta/seed_42 (~500 MB)
# from INKWELL_WEIGHTS_REPO (default Hamshika/inkwell-weights), with HF_TOKEN if the repo is private.
# Needs about 2 GB of memory.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/home/user/.cache/huggingface
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY api/requirements.txt api/requirements-encoders.txt api/
RUN pip install --no-cache-dir -r api/requirements-encoders.txt

COPY --chown=user inkwell/ inkwell/
COPY --chown=user configs/ configs/
COPY --chown=user runs/roberta-five-class-seed42/ runs/roberta-five-class-seed42/
COPY --chown=user api/ api/
COPY --chown=user web/ web/

USER user
EXPOSE 7860
# Hosts such as Render and Cloud Run set $PORT; 7860 otherwise.
CMD ["sh", "-c", "exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
