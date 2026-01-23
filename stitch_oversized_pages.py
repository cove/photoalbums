import re, os, glob, subprocess
from datetime import datetime
from stitching import AffineStitcher
import numpy as np
import cv2

AUTHOR = "Audrey Dean Cordell"
HOME = os.environ["HOME"]
BASE_DIR = HOME + "/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"
MIN_OUTPUT_SIZE = 100 * 1024  # 100 KB
NEW_NAME_RE = re.compile(
    r"^[A-Z]{2,}_\d{4}(?:-\d{4})?_B\d{2}_P\d{2}_S\d{2}\.tif$",
    re.IGNORECASE
)

def add_bottom_header(image, author, stitched_date, header_text="", margin=15):
    """
    Adds a bottom banner to an image with:
    - header_text centered
    - author left
    - stitched_date right
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    img_width = image.shape[1]

    # Font scaling for main header
    font_scale = 2.0
    thickness = 3
    (text_width, text_height), _ = cv2.getTextSize(header_text, font, font_scale, thickness)
    while text_width > img_width - 20 and font_scale > 0.5:
        font_scale -= 0.1
        (text_width, text_height), _ = cv2.getTextSize(header_text, font, font_scale, thickness)

    # Extra space for two lines
    line_spacing = text_height + margin
    new_height = image.shape[0] + 2 * line_spacing + 2 * margin
    new_image = np.zeros((new_height, img_width, 3), dtype=image.dtype)
    new_image[0:image.shape[0], :, :] = image

    # Black rectangle
    y_start = image.shape[0]
    y_end = new_height
    cv2.rectangle(new_image, (0, y_start), (img_width, y_end), (0, 0, 0), -1)

    # Centered main header
    x_header = (img_width - text_width) // 2
    y_header = image.shape[0] + margin + text_height
    cv2.putText(new_image, header_text, (x_header, y_header), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    # Author left, date right
    date_font_scale = font_scale * 0.8
    date_thickness = max(1, int(thickness * 0.7))
    (author_width, _), _ = cv2.getTextSize(author, font, date_font_scale, date_thickness)
    (date_width, _), _ = cv2.getTextSize(stitched_date, font, date_font_scale, date_thickness)

    y_line2 = y_header + line_spacing
    cv2.putText(new_image, author, (margin, y_line2), font, date_font_scale, (255, 255, 255), date_thickness, cv2.LINE_AA)
    cv2.putText(new_image, stitched_date, (img_width - date_width - margin, y_line2), font, date_font_scale, (255, 255, 255), date_thickness, cv2.LINE_AA)

    return new_image

def get_view_dirname(dir):
    base, ext = os.path.splitext(dir)
    if base.endswith("_Archive"):
        base = base[:-8] + "_View"
    return base + ext

def list_page_scans(directory):
    files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and NEW_NAME_RE.fullmatch(f)
    ]

    def extract_page_scan(filename):
        m = re.search(r"_P(\d+)_S(\d+)\.tif$", filename)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    files.sort(key=lambda f: extract_page_scan(f))

    used = set()
    pairs = []

    for i, f1 in enumerate(files):
        if f1 in used:
            continue

        page1, scan1 = extract_page_scan(f1)
        paired = False

        for f2 in files[i + 1:]:
            if f2 in used:
                continue

            page2, scan2 = extract_page_scan(f2)
            if page2 == page1 and scan2 == scan1 + 1:
                pairs.append([
                    os.path.join(directory, f1),
                    os.path.join(directory, f2)
                ])
                used.update([f1, f2])
                paired = True
                break

        if not paired:
            pairs.append([os.path.join(directory, f1)])
            used.add(f1)

    return pairs

def output_is_valid(path):
    return os.path.exists(path) and os.path.getsize(path) > MIN_OUTPUT_SIZE

def tif_to_jpg(tif_path, output_dir):
    import cv2
    import os
    import re
    import subprocess
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(tif_path))[0].replace("Archive", "View")
    jpg_file = os.path.join(output_dir, f"{base_name}.jpg")

    if output_is_valid(jpg_file):
        print("Skipping existing:", os.path.basename(jpg_file))
        return

    # =========================
    # Read TIFF
    # =========================
    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Could not read image")

    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # =========================
    # Extract info from filename
    # =========================
    m = re.match(
        r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d+)_P(?P<page>\d+)_S\d+",
        os.path.basename(tif_path),
        re.IGNORECASE
    )

    if m:
        collection = m.group("collection")
        year = m.group("year")
        book = m.group("book")
        page = m.group("page")
    else:
        collection = "Unknown Collection"
        year = "Unknown Year"
        book = "00"
        page = "00"

    # Header info
    header_text = f"{collection} ({year}) - Book {int(book):02d}, Page {int(page):02d}, Scans S01"
    stitched_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    author_line = f"Original Album Author: {AUTHOR}"

    # =========================
    # Add bottom header
    # =========================
    img = add_bottom_header(img, author_line, f"Creation Date: {stitched_date}", header_text)

    # =========================
    # Save JPEG
    # =========================
    cv2.imwrite(jpg_file, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    # =========================
    # Write provenance metadata
    # =========================
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={AUTHOR}",
        f"-XMP-dc:Description={header_text}",
        jpg_file
    ], check=True)

    print(f"Saved JPEG: {jpg_file}")

def stitch(files, output_dir):
    """
    Stitch a list of TIFF files together, add a bottom banner, save as JPEG, and write metadata.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Extract collection, year, book, and page from first filename
    basename = os.path.basename(files[0])
    m = re.match(
        r"(?P<collection>[A-Z]+)_(?P<year>\d{4})(?:-\d{4})?_B(?P<book>\d+)_P(?P<page>\d+)_S\d+\.tif",
        basename,
        re.IGNORECASE
    )
    if m:
        collection = m.group("collection")
        year = m.group("year")
        book = m.group("book")
        page = m.group("page")
    else:
        collection = "Unknown Collection"
        year = "Unknown Year"
        book = "00"
        page = "00"

    # Base filename for saving
    page_str = f"_P{int(page):02d}"
    base_name = re.sub(r"_P\d+_S\d+\.tif$", "", basename).replace("Archive", "View")
    stitched_file = os.path.join(output_dir, f"{base_name}{page_str}_stitched.jpg")

    print("Stitching...", [os.path.basename(f) for f in files])

    # =========================
    # Stitching attempts
    # =========================
    attempts = [
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.1}
    ]
    combined = None
    for settings in attempts:
        try:
            stitcher = AffineStitcher(**settings)
            combined = stitcher.stitch(files)
            if combined is not None and combined.size > 0:
                break
        except Exception as e:
            print(f"Stitch attempt with {settings} failed: {e}")
            combined = None

    if combined is None:
        raise RuntimeError("All stitching attempts failed")

    # Prepare header info
    scans = [f"S{str(i + 1).zfill(2)}" for i in range(len(files))]
    header_text = f"{collection} ({year}) - Book {int(book):02d}, Page {int(page):02d}, Scans {', '.join(scans)}"
    stitched_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    author_line = f"Original Album Author: {AUTHOR}"

    # Add banner
    combined = add_bottom_header(combined, author_line, f"Stitched Creation Date: {stitched_date}", header_text)

    # Save final stitched image
    cv2.imwrite(stitched_file, combined, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    # Write provenance metadata
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={AUTHOR}",
        f"-XMP-dc:Description={header_text}",
        stitched_file
    ], check=True)

    print(f"Saved stitched image: {stitched_file}")


def extract_page_from_filename(filename):
    m = re.search(r"_P(\d+)_S\d+\.tif$", filename)
    return int(m.group(1)) if m else None

# ================================
# MAIN + SUMMARY
# ================================
if __name__ == "__main__":

    success_count = 0
    failure_count = 0
    failures = []

    for input_dir in glob.glob(BASE_DIR + "/*_Archive"):
        output_dir = get_view_dirname(input_dir)

        for pair in list_page_scans(input_dir):
            try:
                page_number = extract_page_from_filename(
                    os.path.basename(pair[0])
                )

                if len(pair) == 2:
                    stitch(
                        pair,
                        output_dir,
                    )
                else:
                    tif_to_jpg(
                        pair[0],
                        output_dir,
                    )

                success_count += 1

            except Exception as e:
                failure_count += 1
                failures.append({
                    "files": pair,
                    "error": str(e)
                })
                print("Error processing", pair, e)

    print("\n===== STITCH SUMMARY =====")
    print(f"Successful:   {success_count}")
    print(f"Unsuccessful: {failure_count}")

    if failures:
        print("\nFailed items:")
        for f in failures:
            print(" -", ", ".join(os.path.basename(p) for p in f["files"]))
