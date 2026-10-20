"""Assemble a deploy folder with Dockerfile at its root: python -m api.bundle --out dist/deploy [--svm-only]

Used for hosts that build from an uploaded folder (Google Cloud Run --source, a Hugging Face Space).
No weights are included: the full image downloads them from INKWELL_WEIGHTS_REPO with HF_TOKEN at startup.
"""
import argparse
import shutil
from pathlib import Path

from api.app import MODELS
from inkwell.common import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/deploy")
    ap.add_argument("--svm-only", action="store_true", help="light image without torch (api/Dockerfile.svm)")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists(): shutil.rmtree(out)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".cache", "model", "tokenizer")
    for folder in ["inkwell", "configs", "api", "web"]:
        shutil.copytree(ROOT / folder, out / folder, ignore=skip)
    for key, (_, run) in MODELS.items():
        if key == "svm" or not args.svm_only:
            shutil.copytree(ROOT / "runs" / run, out / "runs" / run, ignore=skip)
    shutil.copy(ROOT / ("api/Dockerfile.svm" if args.svm_only else "api/Dockerfile"), out / "Dockerfile")
    shutil.copy(ROOT / "api/README.md", out / "README.md")  # Also the Space card on Hugging Face.
    print(f"Deploy folder ready: {out.resolve()}")


if __name__ == "__main__":
    main()
