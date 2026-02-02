import os, sys
import glob
import subprocess
import tempfile
from pathlib import Path

BASE_DIR=None
if sys.platform.startswith("darwin"):
    HOME = os.environ["HOME"]
    BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"
elif sys.platform.startswith("win"):
    BASE_DIR = f"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums"
    magick_path = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI"
    os.environ["PATH"] = magick_path + os.pathsep + os.environ["PATH"]
else:
    raise NotImplementedError

import re
from pathlib import Path
import subprocess


def tiff_needs_conversion(tiff_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "exiftool",
                "-ExtraSamples",
                "-Compression",
                "-Predictor",
                str(tiff_path),
            ],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.lower()

        # Check for alpha (ExtraSamples containing "alpha" or any number > 0)
        has_alpha = bool(re.search(r"(alpha|\b[1-9]\b)", output))

        # Check compression: must contain "lzw"
        compression_ok = bool(re.search(r"\blzw\b", output))

        # Check predictor: must contain "horizontal differencing"
        predictor_ok = bool(re.search(r"horizontal differencing", output))

        # Needs conversion if alpha exists, compression not LZW, or predictor wrong
        return not compression_ok or not predictor_ok

    except Exception:
        # If exiftool fails, assume conversion needed
        return True


def validate_pixels(original_path: Path, converted_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["magick", "compare", "-metric", "AE",
             str(original_path), str(converted_path), "null:"],
            capture_output=True,
            text=True,
            check=False
        )
        diff_count = int(result.stderr.strip().split()[0])
        return diff_count == 0
    except Exception as e:
        print(f"Validation error for {original_path}: {e}")
        return False


def process_tiff_in_place(tiff_path: Path):
    if not tiff_needs_conversion(tiff_path):
        print(f"Skipped (already correct): {tiff_path}")
        return

    with tempfile.NamedTemporaryFile(
            suffix=".tif",
            dir=tempfile.gettempdir(),
            delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            [
                "magick", str(tiff_path),
                "-alpha", "off",
                "-compress", "lzw",
                "-define", "tiff:predictor=2",
                str(tmp_path)
            ],
            check=True
        )

        if not validate_pixels(tiff_path, tmp_path):
            print(f"Pixel mismatch, not replacing: {tiff_path}")
            tmp_path.unlink(missing_ok=True)
            return

        # Atomic replace
        tmp_path.replace(tiff_path)
        print(f"Processed and replaced: {tiff_path}")

    except subprocess.CalledProcessError as e:
        print(f"Error processing {tiff_path}: {e}")
        tmp_path.unlink(missing_ok=True)


def convert_directory(base_dir: str):
    archive_dirs = glob.glob(f"{base_dir}/*_Archive")

    # Collect all TIFF files from all archive directories
    all_tiffs = []
    for archive_dir in archive_dirs:
        archive_path = Path(archive_dir)
        all_tiffs.extend(archive_path.rglob("*.tif"))

    # Sort by creation time (most recent first)
    all_tiffs.sort(key=lambda p: p.stat().st_ctime, reverse=True)

    # Process in order of most recent first
    for tiff_path in all_tiffs:
        process_tiff_in_place(tiff_path)


def main():
    convert_directory(BASE_DIR)


if __name__ == "__main__":
    main()