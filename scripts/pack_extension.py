"""Pack the Chrome extension into web/inkwell-extension.zip, the download offered on the Guides page.

Run from the repository root after changing anything in extension/:

    python scripts/pack_extension.py

The zip holds one folder, inkwell-extension/, which is what "Load unpacked" in chrome://extensions expects.
"""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extension"
TARGET = ROOT / "web" / "inkwell-extension.zip"
FOLDER = "inkwell-extension"
SKIP = {"README.md"}


def main():
    files = sorted(p for p in SOURCE.rglob("*") if p.is_file() and p.name not in SKIP and "__pycache__" not in p.parts)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            # A fixed date keeps the zip identical when nothing in extension/ changed.
            info = zipfile.ZipInfo(f"{FOLDER}/{path.relative_to(SOURCE).as_posix()}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
    print(f"Wrote {TARGET.relative_to(ROOT)}: {len(files)} files, {TARGET.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
