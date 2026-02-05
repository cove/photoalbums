import os, re, glob, subprocess, sys
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from stitching import AffineStitcher

# =====================
# CONFIG
# =====================
CREATOR = "Audrey D. Cordell"
if sys.platform.startswith("darwin"):
    HOME = os.environ["HOME"]
    BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"
elif sys.platform.startswith("win"):
    BASE_DIR = f"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums"
else:
    raise NotImplementedError

MIN_OUTPUT_SIZE = 100 * 1024  # 100 KB

NEW_NAME_RE = re.compile(
    r"^[A-Z]{2,}_\d{4}(?:-\d{4})?_B(?:\d{2}|∅)_P\d{2}_S\d{2}\.tif$",
    re.IGNORECASE
)

DERIVED_RE = re.compile(r"_D(?P<d1>\d{2})_(?P<d2>\d{2})", re.IGNORECASE)

FILENAME_RE = re.compile(
    r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d{2}|∅)_P(?P<page>\d+)_S\d+",
    re.IGNORECASE
)

FILENAME_RE_NO_SCAN = re.compile(
    r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d{2}|∅)_P(?P<page>\d+)",
    re.IGNORECASE
)
IMAGE_EXTS = (".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")

# =====================
# HELPERS
# =====================
def output_is_valid(path, min_size=MIN_OUTPUT_SIZE):
    return os.path.exists(path) and os.path.getsize(path) > min_size


def get_view_dirname(path):
    base = os.path.basename(path)
    base_no_archive = base.replace("_Archive", "")
    m = re.match(r"^(?P<collection>[A-Za-z]+)_(?P<year>\d{4}(?:-\d{4})?)_(?P<rest>.+)$", base_no_archive)
    if m:
        collection = m.group("collection")
        year = m.group("year")
        rest = m.group("rest")
        return os.path.join(os.path.dirname(path), f"{year}_{collection}_{rest}_View")
    return os.path.join(os.path.dirname(path), f"{base_no_archive}_View")


def parse_filename(filename):
    m = FILENAME_RE.search(filename)
    if not m:
        m = FILENAME_RE_NO_SCAN.search(filename)
    if not m:
        return ("Unknown", "Unknown", "00", "00")
    return m.group("collection"), m.group("year"), m.group("book"), m.group("page")


def add_bottom_header(image, author, date_text, header_text, margin=15):
    """Add header using Pillow for better Unicode support (like ∅)"""
    # Convert from BGR (OpenCV) to RGB (Pillow)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(image_rgb)

    w, h = pil_image.size

    # Try to load a system font that supports Unicode
    font_size = 60
    small_font_size = 48

    # Try to find a good Unicode font with math symbols support
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS - has extensive Unicode
        "/Library/Fonts/Arial Unicode.ttf",  # macOS alternate
        "/System/Library/Fonts/STHeiti Light.ttc",  # macOS - Chinese font with good Unicode
        "/System/Library/Fonts/Apple Symbols.ttf",  # macOS - symbols font
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "/System/Library/Fonts/SFNS.ttf",  # macOS San Francisco
        "C:/Windows/Fonts/arial.ttf",  # Windows
        "C:/Windows/Fonts/seguisym.ttf",  # Windows - Segoe UI Symbol
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux
    ]

    font = None
    small_font = None
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
                small_font = ImageFont.truetype(font_path, small_font_size)
                break
        except:
            continue

    # Fallback to default font if no TrueType font found
    if font is None:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Create a temporary draw object to measure text
    temp_img = Image.new('RGB', (1, 1))
    draw_temp = ImageDraw.Draw(temp_img)

    # Get text bounding box for main header
    bbox = draw_temp.textbbox((0, 0), header_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Scale down font if text is too wide
    while text_width > w - 40 and font_size > 20:
        font_size = int(font_size * 0.9)
        small_font_size = int(font_size * 0.8)
        try:
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    small_font = ImageFont.truetype(font_path, small_font_size)
                    break
        except:
            pass
        bbox = draw_temp.textbbox((0, 0), header_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    # Get small text height for spacing
    small_bbox = draw_temp.textbbox((0, 0), author, font=small_font)
    small_text_height = small_bbox[3] - small_bbox[1]

    # Calculate new image height with extra padding
    line_spacing = margin * 2  # Extra space between lines
    footer_height = text_height + small_text_height + (margin * 4) + line_spacing
    new_h = h + footer_height

    # Create new image with black footer
    new_image = Image.new('RGB', (w, new_h), color='black')
    new_image.paste(pil_image, (0, 0))

    # Draw on the new image
    draw = ImageDraw.Draw(new_image)

    # Draw main header text (centered) - position from top of footer area
    y1 = h + margin * 2
    x1 = (w - text_width) // 2
    draw.text((x1, y1), header_text, fill='white', font=font)

    # Draw author text (left) - position below main text
    y2 = y1 + text_height + line_spacing
    draw.text((margin, y2), author, fill='white', font=small_font)

    # Draw date text (right)
    date_bbox = draw_temp.textbbox((0, 0), date_text, font=small_font)
    date_width = date_bbox[2] - date_bbox[0]
    draw.text((w - date_width - margin, y2), date_text, fill='white', font=small_font)

    # Convert back to BGR (OpenCV format)
    result = np.array(new_image)
    result = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

    return result


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

def list_derived_images(directory):
    files = []
    for name in os.listdir(directory):
        if not name.lower().endswith(IMAGE_EXTS):
            continue
        if not DERIVED_RE.search(name):
            continue
        files.append(os.path.join(directory, name))

    def key(path):
        base = os.path.basename(path)
        m_page = FILENAME_RE.search(base) or FILENAME_RE_NO_SCAN.search(base)
        m_d = DERIVED_RE.search(base)
        page = int(m_page.group("page")) if m_page else 0
        d1 = int(m_d.group("d1")) if m_d else 0
        d2 = int(m_d.group("d2")) if m_d else 0
        return page, d1, d2, base.lower()

    files.sort(key=key)
    return files


# =====================
# IMAGE OUTPUT
# =====================
def write_jpeg(image, path, header_text, quality=95):
    cv2.imwrite(path, image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={CREATOR}",
        f"-XMP-dc:Description={header_text}",
        path
    ], check=True)


def tif_to_jpg(tif_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    collection, year, book, page = parse_filename(tif_path)
    out = os.path.join(
        output_dir,
        f"{year}_{collection}_B{book}_P{int(page):02d}.jpg"
    )

    # Get scan number from filename
    m = re.search(r"_S(\d+)", tif_path)
    scan_num = int(m.group(1)) if m else 1

    # Build scans text for JPG
    scans_text = f"S{scan_num:02d}"
    # Format book number - use Ø (more widely supported) for empty set, otherwise format as 2-digit number
    book_display = "Ø" if book == "∅" else f"{int(book):02d}"
    jpg_header = f"{collection} ({year}) - Book {book_display}, Page {int(page):02d}, Scans {scans_text}"

    if output_is_valid(out):
        print(f"{collection} B{book} P{int(page):02d} OK")
        return

    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Could not read image")

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    img = add_bottom_header(
        img,
        f"Creator: {CREATOR}",
        f"Stitched: {datetime.now():%Y-%m-%d %H:%M:%S}",
        jpg_header
    )

    write_jpeg(img, out, jpg_header)

    print(f"{collection} B{book} P{int(page):02d} OK")

def derived_to_jpg(src_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.basename(src_path)
    collection, year, book, page = parse_filename(base)
    m_d = DERIVED_RE.search(base)
    d1 = m_d.group("d1") if m_d else "00"
    d2 = m_d.group("d2") if m_d else "00"

    if collection != "Unknown":
        out_name = f"{year}_{collection}_B{book}_P{int(page):02d}_D{d1}_{d2}.jpg"
    else:
        stem, _ = os.path.splitext(base)
        m_view = re.match(r"^(?P<collection>[A-Za-z]+)_(?P<year>\d{4}(?:-\d{4})?)_(?P<rest>.+)$", stem)
        if m_view:
            out_name = f"{m_view.group('year')}_{m_view.group('collection')}_{m_view.group('rest')}_D{d1}_{d2}.jpg"
        else:
            out_name = f"{stem}_D{d1}_{d2}.jpg"

    out = os.path.join(output_dir, out_name)

    if output_is_valid(out, min_size=1):
        if collection != "Unknown":
            print(f"{collection} B{book} P{int(page):02d} D{d1}_{d2} OK")
        else:
            print(f"{out_name} OK")
        return

    img = cv2.imread(src_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # No footer for derived images.
    if collection != "Unknown":
        book_display = "Ø" if book == "∅" else f"{int(book):02d}"
        desc = (
            f"{collection} ({year}) - Book {book_display}, "
            f"Page {int(page):02d}, Detail D{d1}_{d2}"
        )
    else:
        desc = ""

    original_size = os.path.getsize(src_path)
    quality = 80
    write_jpeg(img, out, desc, quality=quality)

    # Ensure derived output is smaller than original when possible.
    while os.path.exists(out) and os.path.getsize(out) >= original_size and quality > 40:
        quality -= 10
        write_jpeg(img, out, desc, quality=quality)

    if collection != "Unknown":
        print(f"{collection} B{book} P{int(page):02d} D{d1}_{d2} OK")
    else:
        print(f"{out_name} OK")

def stitch(files, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    collection, year, book, page = parse_filename(files[0])

    out = os.path.join(
        output_dir,
        f"{year}_{collection}_B{book}_P{int(page):02d}_stitched.jpg"
    )

    # Get scan numbers for the files being stitched
    scan_nums = []
    for f in files:
        m = re.search(r"_S(\d+)", f)
        if m:
            scan_nums.append(int(m.group(1)))

    # Format: "Scans S01 S02 S03 of 3 total"
    scans_text = " ".join(f"S{s:02d}" for s in scan_nums)
    # Format book number - use Ø (more widely supported) for images, ∅ for metadata
    book_display = "Ø" if book == "∅" else f"{int(book):02d}"
    header = f"{collection} ({year}) - Book {book_display}, Page {int(page):02d}, Scans {scans_text}"

    if output_is_valid(out):
        print(f"{collection} B{book} P{int(page):02d} OK")
        return

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

    result = add_bottom_header(
        result,
        f"Creator: {CREATOR}",
        f"Stitched: {datetime.now():%Y-%m-%d %H:%M:%S}",
        header
    )

    write_jpeg(result, out, header)

    print(f"{collection} B{book} P{int(page):02d} OK")

def dir_created_ts(p: str) -> float:
    """
    Return a sortable timestamp for "created".
    - macOS: st_birthtime if available
    - Windows: st_ctime is creation time
    - Linux: no true creation time; fall back to mtime
    """
    st = os.stat(p)
    # macOS (and some BSDs) expose birth time
    if hasattr(st, "st_birthtime"):
        return float(st.st_birthtime)
    # Windows: st_ctime is creation time; Linux: it's metadata-change time
    # so prefer mtime on Linux-ish systems.
    if sys.platform.startswith("win"):
        return float(st.st_ctime)
    return float(st.st_mtime)

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    success = failures = 0
    failed = []

    # Get all archive directories
    archive_dirs = glob.glob(f"{BASE_DIR}/*_Archive")

    archive_dirs.sort(key=dir_created_ts, reverse=True)

    for archive in archive_dirs:
        view = get_view_dirname(archive)

        for group in list_page_scans(archive):
            try:
                if len(group) > 1:
                    stitch(group, view)
                else:
                    tif_to_jpg(group[0], view)
                success += 1
            except Exception as e:
                failures += 1
                failed.append(group)
                print("Error:", e)

        for derived in list_derived_images(archive):
            try:
                derived_to_jpg(derived, view)
                success += 1
            except Exception as e:
                failures += 1
                failed.append([derived])
                print("Error:", e)

    print("\n===== SUMMARY =====")
    print("Successful:", success)
    print("Failed:", failures)
    if failed:
        print("\n===== FAILURES (DETAILS) =====")
        for group in failed:
            if group:
                c, y, b, p = parse_filename(group[0])
                base = f"{y}_{c}_B{b}_P{int(p):02d}"
            else:
                base = "Unknown"
            print(f"FAILED: {base}")
            print("Files:")
            for f in group:
                print(f"  - {f}")
    for f in failed:
        print(" -", ", ".join(os.path.basename(x) for x in f))
