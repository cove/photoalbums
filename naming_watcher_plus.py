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

COLOR_GREEN = "\x1b[32m"
COLOR_RED = "\x1b[31m"
COLOR_YELLOW = "\x1b[33m"
COLOR_RESET = "\x1b[0m"


def _supports_color():
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _colorize(text, color):
    if not _supports_color():
        return text
    return f"{color}{text}{COLOR_RESET}"


def log_ok(message):
    print(_colorize(message, COLOR_GREEN))


def log_warn(message):
    print(_colorize(message, COLOR_YELLOW))


def log_error(message):
    print(_colorize(message, COLOR_RED))


def log_info(message):
    print(message)


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
        log_error(f"{original_path.name} validation error: {e}")
        return False


def process_tiff_in_place(tiff_path: Path) -> bool:
    if not tiff_needs_conversion(tiff_path):
        return True

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
            log_error(f"{tiff_path.name} pixel mismatch; not replacing")
            tmp_path.unlink(missing_ok=True)
            return False

        tmp_path.replace(tiff_path)
        return True

    except subprocess.CalledProcessError as e:
        log_error(f"{tiff_path.name} processing error: {e}")
        tmp_path.unlink(missing_ok=True)
        return False


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


def validate_stitch(files) -> bool:
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
                return True
        except Exception:
            continue

    return False


class IncomingScanHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.retry_pages = {}

    def _get_retry_filename(self, watch_dir, page_num):
        files = list_page_scans(watch_dir, page_num)
        if files:
            last = files[-1]
            m = PAGE_SCAN_RE.search(last)
            scan = (int(m.group("scan")) if m else 1) + 1
        else:
            scan = 1
        prefix = derive_prefix(watch_dir)
        return f"{prefix}_P{page_num:02d}_S{scan:02d}.tif"

    def on_created(self, event):
        if event.is_directory:
            return
        if os.path.basename(event.src_path).lower() != INCOMING_NAME.lower():
            return

        time.sleep(2.0)

        watch_dir = os.path.dirname(event.src_path)
        retry_page = self.retry_pages.get(watch_dir)
        if retry_page is not None:
            new_name = self._get_retry_filename(watch_dir, retry_page)
        else:
            new_name = get_next_filename(watch_dir)
        old_path = os.path.join(watch_dir, INCOMING_NAME)
        new_path = os.path.join(watch_dir, new_name)

        os.rename(old_path, new_path)

        if not process_tiff_in_place(Path(new_path)):
            log_error(f"{Path(new_name).name} ERROR")
            return

        open_image_fullscreen(new_path)

        page_match = PAGE_SCAN_RE.search(new_name)
        if not page_match:
            log_ok(f"{Path(new_name).name} OK")
            return

        page_num = int(page_match.group("page"))
        files = list_page_scans(watch_dir, page_num)
        if len(files) >= 2:
            if validate_stitch(files):
                if retry_page == page_num:
                    self.retry_pages.pop(watch_dir, None)
                log_ok(f"{Path(new_name).name} OK")
            else:
                self.retry_pages[watch_dir] = page_num
                log_error(f"{Path(new_name).name} STITCH FAILED")
        else:
            log_ok(f"{Path(new_name).name} OK")


def main():
    configure_imagemagick()
    log_info(f"Watching for {INCOMING_NAME} in:")
    log_info(WATCH_ROOT)

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
