"""Assemble a deploy folder with Dockerfile at its root:
    python -m api.bundle --out dist/deploy [--svm-only | --with-weights]

Used for hosts that build from an uploaded folder (Google Cloud Run --source, a Hugging Face Space).
By default encoder weights are left out and the full image downloads them from INKWELL_WEIGHTS_REPO.
--with-weights copies runs/<run>/model and tokenizer into the folder so they are baked into the image;
only deploy such a folder to a private registry (OPP-115-derived checkpoints are research-only).
"""
import argparse
import shutil
from pathlib import Path

from api.app import MODELS
from inkwell.common import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/deploy")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--svm-only", action="store_true", help="light image without torch (api/Dockerfile.svm)")
    mode.add_argument("--with-weights", action="store_true", help="bake local encoder weights into the image")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists(): shutil.rmtree(out)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "model", "tokenizer")
    for folder in ["inkwell", "configs", "api", "web"]:
        shutil.copytree(ROOT / folder, out / folder, ignore=skip)
    for key, (_, run) in MODELS.items():
        if key == "svm" or not args.svm_only:
            shutil.copytree(ROOT / "runs" / run, out / "runs" / run,
                            ignore=shutil.ignore_patterns("__pycache__") if args.with_weights else skip)
            if args.with_weights and key != "svm" and not (out / "runs" / run / "model").is_dir():
                raise SystemExit(f"--with-weights: runs/{run}/model is missing (see Documentation/DEPLOYMENT.md step 1)")
    shutil.copy(ROOT / ("api/Dockerfile.svm" if args.svm_only else "api/Dockerfile"), out / "Dockerfile")
    shutil.copy(ROOT / "api/README.md", out / "README.md")  # Also the Space card on Hugging Face.
    print(f"Deploy folder ready: {out.resolve()}")


if __name__ == "__main__":
    main()
