import os
import re
import time
import subprocess
import tempfile
import sys
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from stitching import AffineStitcher

# Watch all book directories under this root.
WATCH_ROOT = r"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums"
INCOMING_NAME = "incoming_scan.tif"

# Regex to match filenames like: Europe_1973_Bxx_P05_S02.tif
FILENAME_PATTERN = re.compile(
    r"^(?P<prefix>.+)_P(?P<page>\d{2})_S(?P<scan>\d{2})\.tif$", re.IGNORECASE
)

PAGE_SCAN_RE = re.compile(r"_P(?P<page>\d+)_S(?P<scan>\d+)", re.IGNORECASE)


def configure_imagemagick():
    if sys.platform.startswith("win"):
        magick_path = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI"
        os.environ["PATH"] = magick_path + os.pathsep + os.environ["PATH"]


def open_image_fullscreen(path):
    xnview = r"C:\Program Files\XnViewMP\xnviewmp.exe"

    if os.path.exists(xnview):
        subprocess.Popen([xnview, path])
    else:
        os.startfile(path)


def derive_prefix(dir_path):
    base = os.path.basename(dir_path)
    if base.lower().endswith("_archive"):
        base = base[: -len("_archive")]
    return base


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
            check=True,
        )

        output = result.stdout.lower()
        has_alpha = bool(re.search(r"(alpha|\b[1-9]\b)", output))
        compression_ok = bool(re.search(r"\blzw\b", output))
        predictor_ok = bool(re.search(r"horizontal differencing", output))

        return has_alpha or (not compression_ok) or (not predictor_ok)
    except Exception:
        return True


def validate_pixels(original_path: Path, converted_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "magick",
                "compare",
                "-metric",
                "AE",
                str(original_path),
                str(converted_path),
                "null:",
            ],
            capture_output=True,
            text=True,
            check=False,
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
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            [
                "magick",
                str(tiff_path),
                "-alpha",
                "off",
                "-compress",
                "lzw",
                "-define",
                "tiff:predictor=2",
                str(tmp_path),
            ],
            check=True,
        )

        if not validate_pixels(tiff_path, tmp_path):
            print(f"Pixel mismatch, not replacing: {tiff_path}")
            tmp_path.unlink(missing_ok=True)
            return

        tmp_path.replace(tiff_path)
        print(f"Processed and replaced: {tiff_path}")

    except subprocess.CalledProcessError as e:
        print(f"Error processing {tiff_path}: {e}")
        tmp_path.unlink(missing_ok=True)


def get_next_filename(watch_dir):
    """Determine the next filename based on existing files in the directory."""
    files = [f for f in os.listdir(watch_dir) if f.lower().endswith(".tif")]

    valid_files = []
    for f in files:
        match = FILENAME_PATTERN.match(f)
        if match:
            valid_files.append(f)

    if not valid_files:
        # No files yet - start with cover (page 01, scan 01)
        prefix = derive_prefix(watch_dir)
        return f"{prefix}_P01_S01.tif"

    valid_files.sort()
    last_file = valid_files[-1]

    match = FILENAME_PATTERN.match(last_file)
    prefix = match.group("prefix")
    page = int(match.group("page"))
    scan = int(match.group("scan"))

    # Determine next scan/page (cover is single scan P01_S01)
    if page == 1:
        page = 2
        scan = 1
    else:
        if scan < 2:
            scan += 1
        else:
            page += 1
            scan = 1

    return f"{prefix}_P{page:02d}_S{scan:02d}.tif"


def list_page_scans(directory, page_num):
    files = []
    for f in os.listdir(directory):
        if not f.lower().endswith(".tif"):
            continue
        m = PAGE_SCAN_RE.search(f)
        if not m:
            continue
        if int(m.group("page")) == page_num:
            files.append(os.path.join(directory, f))

    def key(f):
        m = PAGE_SCAN_RE.search(f)
        return int(m.group("scan")) if m else 0

    files.sort(key=key)
    return files


def validate_stitch(files):
    if len(files) < 2:
        return True

    attempts = [
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.1},
    ]

    for cfg in attempts:
        try:
            result = AffineStitcher(**cfg).stitch(files)
            if result is not None and getattr(result, "size", 0):
                print("OK: stitch " + ", ".join(os.path.basename(f) for f in files))
                return True
        except Exception:
            continue

    print("Error: failed to stitch " + ", ".join(os.path.basename(f) for f in files))
    return False


class IncomingScanHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if os.path.basename(event.src_path).lower() != INCOMING_NAME.lower():
            return

        time.sleep(5.0)

        watch_dir = os.path.dirname(event.src_path)
        new_name = get_next_filename(watch_dir)
        old_path = os.path.join(watch_dir, INCOMING_NAME)
        new_path = os.path.join(watch_dir, new_name)

        print(f"Renaming {INCOMING_NAME} -> {new_name}")
        os.rename(old_path, new_path)

        process_tiff_in_place(Path(new_path))
        open_image_fullscreen(new_path)

        page_match = PAGE_SCAN_RE.search(new_name)
        if not page_match:
            return

        page_num = int(page_match.group("page"))
        files = list_page_scans(watch_dir, page_num)
        if len(files) >= 2:
            validate_stitch(files)


def main():
    configure_imagemagick()
    print(f"Watching for {INCOMING_NAME} in:")
    print(WATCH_ROOT)

    event_handler = IncomingScanHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_ROOT, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
