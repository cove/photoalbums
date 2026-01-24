import os, re, glob, subprocess
from datetime import datetime
import cv2
import numpy as np
from stitching import AffineStitcher

# =====================
# CONFIG
# =====================
AUTHOR = "Audrey D. Cordell"
HOME = os.environ["HOME"]
BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"
MIN_OUTPUT_SIZE = 100 * 1024  # 100 KB

NEW_NAME_RE = re.compile(
    r"^[A-Z]{2,}_\d{4}(?:-\d{4})?_B\d{2}_P\d{2}_S\d{2}\.tif$",
    re.IGNORECASE
)

FILENAME_RE = re.compile(
    r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d+)_P(?P<page>\d+)_S\d+",
    re.IGNORECASE
)

# =====================
# HELPERS
# =====================
def output_is_valid(path):
    return os.path.exists(path) and os.path.getsize(path) > MIN_OUTPUT_SIZE


def get_view_dirname(path):
    return path.replace("_Archive", "_View")


def parse_filename(filename):
    m = FILENAME_RE.search(filename)
    if not m:
        return ("Unknown", "Unknown", "00", "00")
    return m.group("collection"), m.group("year"), m.group("book"), m.group("page")


def add_bottom_header(image, author, date_text, header_text, margin=15):
    font = cv2.FONT_HERSHEY_SIMPLEX
    w = image.shape[1]

    scale, thickness = 2.0, 3
    (tw, th), _ = cv2.getTextSize(header_text, font, scale, thickness)
    while tw > w - 20 and scale > 0.5:
        scale -= 0.1
        (tw, th), _ = cv2.getTextSize(header_text, font, scale, thickness)

    line_h = th + margin
    new_h = image.shape[0] + 2 * line_h + 2 * margin
    out = np.zeros((new_h, w, 3), dtype=image.dtype)
    out[:image.shape[0]] = image

    cv2.rectangle(out, (0, image.shape[0]), (w, new_h), (0, 0, 0), -1)

    y1 = image.shape[0] + margin + th
    cv2.putText(out, header_text, ((w - tw) // 2, y1),
                font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    small_scale = scale * 0.8
    small_thick = max(1, int(thickness * 0.7))
    y2 = y1 + line_h

    cv2.putText(out, author, (margin, y2),
                font, small_scale, (255, 255, 255), small_thick, cv2.LINE_AA)

    (dw, _), _ = cv2.getTextSize(date_text, font, small_scale, small_thick)
    cv2.putText(out, date_text, (w - dw - margin, y2),
                font, small_scale, (255, 255, 255), small_thick, cv2.LINE_AA)

    return out


def list_page_scans(directory):
    files = sorted(
        f for f in os.listdir(directory)
        if NEW_NAME_RE.fullmatch(f)
    )

    def key(f):
        m = re.search(r"_P(\d+)_S(\d+)", f)
        return int(m.group(1)), int(m.group(2))

    files.sort(key=key)

    pages = {}
    for f in files:
        p, _ = key(f)
        pages.setdefault(p, []).append(os.path.join(directory, f))

    return list(pages.values())


# =====================
# IMAGE OUTPUT
# =====================
def write_jpeg(image, path, header_text):
    cv2.imwrite(path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={AUTHOR}",
        f"-XMP-dc:Description={header_text}",
        path
    ], check=True)


def tif_to_jpg(tif_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(
        output_dir,
        os.path.splitext(os.path.basename(tif_path))[0].replace("Archive", "View") + ".jpg"
    )

    if output_is_valid(out):
        print("Skipping existing:", os.path.basename(out))
        return

    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Could not read image")

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    collection, year, book, page = parse_filename(tif_path)
    header = f"{collection} ({year}) - Book {int(book):02d}, Page {int(page):02d}, Scans S01"

    img = add_bottom_header(
        img,
        f"Album Author: {AUTHOR}",
        f"Stitched: {datetime.now():%Y-%m-%d %H:%M:%S}",
        header
    )

    write_jpeg(img, out, header)
    print("Saved:", out)


def stitch(files, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    collection, year, book, page = parse_filename(files[0])
    base = re.sub(r"_P\d+_S\d+\.tif$", "", os.path.basename(files[0]))
    out = os.path.join(output_dir, f"{base}_P{int(page):02d}_stitched.jpg")

    if output_is_valid(out):
        print("Skipping existing:", os.path.basename(out))
        return

    print("Stitching:", [os.path.basename(f) for f in files])

    attempts = [
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.1},
    ]

    result = None
    for cfg in attempts:
        try:
            result = AffineStitcher(**cfg).stitch(files)
            if result is not None and result.size:
                break
        except Exception:
            pass

    if result is None:
        raise RuntimeError("All stitching attempts failed")

    scans = ", ".join(f"S{str(i+1).zfill(2)}" for i in range(len(files)))
    header = f"{collection} ({year}) - Book {int(book):02d}, Page {int(page):02d}, Scans {scans}"

    result = add_bottom_header(
        result,
        f"Album Author: {AUTHOR}",
        f"Stitched: {datetime.now():%Y-%m-%d %H:%M:%S}",
        header
    )

    write_jpeg(result, out, header)
    print("Saved stitched:", out)


# =====================
# MAIN
# =====================
if __name__ == "__main__":
    success = failures = 0
    failed = []

    for archive in glob.glob(f"{BASE_DIR}/*_Archive"):
        view = get_view_dirname(archive)

        for group in list_page_scans(archive):
            try:
                stitch(group, view) if len(group) > 1 else tif_to_jpg(group[0], view)
                success += 1
            except Exception as e:
                failures += 1
                failed.append(group)
                print("Error:", e)

    print("\n===== SUMMARY =====")
    print("Successful:", success)
    print("Failed:", failures)
    for f in failed:
        print(" -", ", ".join(os.path.basename(x) for x in f))
