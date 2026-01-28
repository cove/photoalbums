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

FILENAME_RE = re.compile(
    r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d{2}|∅)_P(?P<page>\d+)_S\d+",
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


def count_totals(archive_dirs):
    """Count total pages and scans per page for each collection/book"""
    totals = {}

    for archive in archive_dirs:
        files = [f for f in os.listdir(archive) if NEW_NAME_RE.fullmatch(f)]

        for f in files:
            collection, year, book, page = parse_filename(f)
            key = f"{collection}_{year}_B{book}"

            if key not in totals:
                totals[key] = {"pages": set(), "page_scans": {}}

            m = re.search(r"_P(\d+)_S(\d+)", f)
            if m:
                page_num = int(m.group(1))
                scan_num = int(m.group(2))
                totals[key]["pages"].add(page_num)

                # Track max scan number for each page
                if page_num not in totals[key]["page_scans"]:
                    totals[key]["page_scans"][page_num] = 0
                totals[key]["page_scans"][page_num] = max(totals[key]["page_scans"][page_num], scan_num)

    # Convert sets to counts
    for key in totals:
        totals[key]["total_pages"] = len(totals[key]["pages"])
        del totals[key]["pages"]

    return totals


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


# =====================
# IMAGE OUTPUT
# =====================
def write_jpeg(image, path, header_text):
    cv2.imwrite(path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={CREATOR}",
        f"-XMP-dc:Description={header_text}",
        path
    ], check=True)


def get_tif_description(tif_path):
    """Get current XMP Description from TIFF file"""
    try:
        result = subprocess.run([
            "exiftool",
            "-XMP-dc:Description",
            "-s3",  # Short format, values only
            tif_path
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return None


def get_tif_creator(tif_path):
    """Get current XMP Creator from TIFF file"""
    try:
        result = subprocess.run([
            "exiftool",
            "-XMP-dc:Creator",
            "-s3",  # Short format, values only
            tif_path
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return None


def update_tif_metadata(tif_path, header_text):
    """Update XMP metadata in TIFF file only if different, preserving all existing metadata"""
    current_desc = get_tif_description(tif_path)
    current_creator = get_tif_creator(tif_path)

    # Check if Creator has been duplicated (contains the name more than once)
    creator_needs_fix = False
    if current_creator and current_creator.count(CREATOR) > 1:
        creator_needs_fix = True

    # Check if we need to update at all
    if current_desc == header_text and not creator_needs_fix and current_creator == CREATOR:
        return False  # No update needed

    # If Creator is duplicated, clear it first then set it
    if creator_needs_fix:
        subprocess.run([
            "exiftool",
            "-overwrite_original",
            "-XMP-dc:Creator=",  # Clear the field
            tif_path
        ], check=True)

    # Set Creator and Description
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={CREATOR}",
        f"-XMP-dc:Description={header_text}",
        tif_path
    ], check=True)

    return True  # Updated


def tif_to_jpg(tif_path, output_dir, totals):
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(
        output_dir,
        os.path.splitext(os.path.basename(tif_path))[0].replace("Archive", "View") + ".jpg"
    )

    collection, year, book, page = parse_filename(tif_path)
    key = f"{collection}_{year}_B{book}"
    total_pages = totals.get(key, {}).get("total_pages", 0)
    page_num = int(page)
    total_scans_for_page = totals.get(key, {}).get("page_scans", {}).get(page_num, 1)

    # Get scan number from filename
    m = re.search(r"_S(\d+)", tif_path)
    scan_num = int(m.group(1)) if m else 1

    # Build scans text for JPG - list all scans for this page
    scans_text = " ".join(f"S{s:02d}" for s in range(1, total_scans_for_page + 1))
    # Format book number - use Ø (more widely supported) for empty set, otherwise format as 2-digit number
    book_display = "Ø" if book == "∅" else f"{int(book):02d}"
    jpg_header = f"{collection} ({year}) - Book {book_display}, Page {int(page):02d} of {total_pages:02d}, Scans {scans_text} of {total_scans_for_page} total"

    # Build header for TIFF - use ∅ in metadata (text-only, no rendering issues)
    tif_book_display = book if book == "∅" else f"{int(book):02d}"
    tif_header = f"{collection} ({year}) - Book {tif_book_display}, Page {int(page):02d} of {total_pages:02d}, Scan S{scan_num:02d} of {total_scans_for_page} total"

    if output_is_valid(out):
        print("Skipping existing:", os.path.basename(out))
        # Still update TIFF metadata even if JPG exists
        try:
            if update_tif_metadata(tif_path, tif_header):
                print(f"  Updated TIFF metadata for {os.path.basename(tif_path)}")
            else:
                print(f"  TIFF metadata already current for {os.path.basename(tif_path)}")
        except Exception as e:
            print(f"  Warning: Could not update TIFF metadata for {os.path.basename(tif_path)}: {e}")
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

    # Update TIFF metadata
    try:
        if update_tif_metadata(tif_path, tif_header):
            print("  Updated TIFF metadata")
        else:
            print("  TIFF metadata already current")
    except Exception as e:
        print(f"  Warning: Could not update TIFF metadata: {e}")

    print("Saved:", out)


def stitch(files, output_dir, totals):
    os.makedirs(output_dir, exist_ok=True)

    collection, year, book, page = parse_filename(files[0])
    key = f"{collection}_{year}_B{book}"
    total_pages = totals.get(key, {}).get("total_pages", 0)
    page_num = int(page)
    total_scans_for_page = totals.get(key, {}).get("page_scans", {}).get(page_num, len(files))

    base = re.sub(r"_P\d+_S\d+\.tif$", "", os.path.basename(files[0]))
    out = os.path.join(output_dir, f"{base}_P{int(page):02d}_stitched.jpg")

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
    header = f"{collection} ({year}) - Book {book_display}, Page {int(page):02d} of {total_pages:02d}, Scans {scans_text} of {total_scans_for_page} total"

    # For TIFF metadata, use the actual ∅ symbol
    tif_book_display = book if book == "∅" else f"{int(book):02d}"

    if output_is_valid(out):
        print("Skipping existing:", os.path.basename(out))
        # Still update TIFF metadata for all source files
        for tif_path in files:
            m = re.search(r"_S(\d+)", tif_path)
            scan_num = int(m.group(1)) if m else 1
            # Each TIFF shows only its own scan number - use ∅ in metadata
            tif_header = f"{collection} ({year}) - Book {tif_book_display}, Page {int(page):02d} of {total_pages:02d}, Scan S{scan_num:02d} of {total_scans_for_page} total"
            try:
                if update_tif_metadata(tif_path, tif_header):
                    print(f"  Updated TIFF metadata for {os.path.basename(tif_path)}")
                else:
                    print(f"  TIFF metadata already current for {os.path.basename(tif_path)}")
            except Exception as e:
                print(f"  Warning: Could not update TIFF metadata for {os.path.basename(tif_path)}: {e}")
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

    result = add_bottom_header(
        result,
        f"Creator: {CREATOR}",
        f"Stitched: {datetime.now():%Y-%m-%d %H:%M:%S}",
        header
    )

    write_jpeg(result, out, header)

    # Update TIFF metadata for all source files
    for tif_path in files:
        m = re.search(r"_S(\d+)", tif_path)
        scan_num = int(m.group(1)) if m else 1
        # Each TIFF shows only its own scan number - use ∅ in metadata
        tif_header = f"{collection} ({year}) - Book {tif_book_display}, Page {int(page):02d} of {total_pages:02d}, Scan S{scan_num:02d} of {total_scans_for_page} total"
        try:
            if update_tif_metadata(tif_path, tif_header):
                print(f"  Updated TIFF metadata for {os.path.basename(tif_path)}")
            else:
                print(f"  TIFF metadata already current for {os.path.basename(tif_path)}")
        except Exception as e:
            print(f"  Warning: Could not update TIFF metadata for {os.path.basename(tif_path)}: {e}")

    print("Saved stitched:", out)


# =====================
# MAIN
# =====================
if __name__ == "__main__":
    success = failures = 0
    failed = []

    # Get all archive directories
    archive_dirs = glob.glob(f"{BASE_DIR}/*_Archive")

    # Count totals across all archives
    print("Counting total pages and scans per book...")
    totals = count_totals(archive_dirs)

    for key, data in totals.items():
        total_scans = sum(data['page_scans'].values())
        print(f"{key}: {data['total_pages']} pages, {total_scans} total scans")
    print()

    for archive in archive_dirs:
        view = get_view_dirname(archive)

        for group in list_page_scans(archive):
            try:
                if len(group) > 1:
                    stitch(group, view, totals)
                else:
                    tif_to_jpg(group[0], view, totals)
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
