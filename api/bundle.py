"""Assemble a deploy folder with Dockerfile at its root: python -m api.bundle --out dist/deploy

Used for hosts that build from an uploaded folder (Google Cloud Run --source, a Hugging Face Space).
No weights are included: the image downloads them from INKWELL_WEIGHTS_REPO with HF_TOKEN at startup.
"""
import argparse
import shutil
from pathlib import Path

from api.app import MODELS
from inkwell.common import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/deploy")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists(): shutil.rmtree(out)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".cache", "model", "tokenizer")
    for folder in ["inkwell", "configs", "api", "web"]:
        shutil.copytree(ROOT / folder, out / folder, ignore=skip)
    for _, run in MODELS.values():
        shutil.copytree(ROOT / "runs" / run, out / "runs" / run, ignore=skip)
    shutil.copy(ROOT / "api/Dockerfile", out / "Dockerfile")
    shutil.copy(ROOT / "api/README.md", out / "README.md")  # Also the Space card on Hugging Face.
    print(f"Deploy folder ready: {out.resolve()}")


if __name__ == "__main__":
    main()
