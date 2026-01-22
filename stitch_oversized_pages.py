import cv2
import re, os, glob, subprocess
from stitching import AffineStitcher

HOME = os.environ["HOME"]
BASE_DIR = HOME + "/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"

AUTHOR = "Audrey Dean Cordell"

def get_view_dirname(dir):
    base, ext = os.path.splitext(dir)
    if base.endswith("_Archive"):
        base = base[:-8] + "_View"
    return base + ext

# Regex to match new naming convention: YEAR(_YEAR)?_Name_B01_P00_S01.tif
NEW_NAME_RE = re.compile(
    r"^\d{4}(?:_\d{4})?_.+_B\d+_P\d+_S\d+\.tif$", re.IGNORECASE
)

def list_sequential_file_pairs_and_partials(directory):
    files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and NEW_NAME_RE.fullmatch(f)
    ]

    def extract_page_scan(filename):
        """Return (page_number, scan_number) from filename"""
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
            # Only pair if same page, sequential scans (S01 -> S02)
            if page1 is not None and page2 == page1 and scan2 == scan1 + 1:
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

def tif_to_jpg(tif_path, output_dir, book="Unknown", page=0, scans=None):
    os.makedirs(output_dir, exist_ok=True)

    # Determine output filename
    base_name = os.path.splitext(os.path.basename(tif_path))[0].replace("Archive", "View")
    jpg_file = os.path.join(output_dir, f"{base_name}.jpg")

    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Could not read image: {tif_path}")

    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    cv2.imwrite(jpg_file, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    # Add XMP metadata via ExifTool
    provenance = f"Book {book}, Page {page}, Scans S01"
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={AUTHOR}",
        f"-XMP-dc:Description={provenance}",
        jpg_file
    ], check=True)

    print(f"Saved single-scan JPG with metadata: {jpg_file}")
    return jpg_file

def stitch(files, output_dir, book="Unknown", page=0):
    os.makedirs(output_dir, exist_ok=True)

    # Extract page number from first file (assumes all files are from the same page)
    m = re.search(r"(_P\d+)_S\d+\.tif$", os.path.basename(files[0]))
    page_str = m.group(1) if m else f"_P{page:02d}"

    # Base name without the page/scan part
    base_name = re.sub(r"_P\d+_S\d+\.tif$", "", os.path.basename(files[0])).replace("Archive", "View")

    stitched_file = os.path.join(output_dir, f"{base_name}{page_str}_stitched.jpg")

    if os.path.exists(stitched_file) and os.path.getsize(stitched_file) > 100_000:
        print(f"Skipping existing stitched file: {stitched_file}")
        return

    print("Stitching...", files)
    attempts = [
        {"detector": "sift", "confidence_threshold": 0.4},
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.2},
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
            print(f"Failed with settings {settings}: {e}")

    if combined is None:
        raise RuntimeError("Stitching failed with all detector settings")

    cv2.imwrite(stitched_file, combined, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    # XMP metadata
    scans = [f"S{str(i + 1).zfill(2)}" for i in range(len(files))]
    provenance = f"Book {book}, Page {page}, Scans {', '.join(scans)}"
    subprocess.run([
        "exiftool",
        "-overwrite_original",
        f"-XMP-dc:Creator={AUTHOR}",
        f"-XMP-dc:Description={provenance}",
        stitched_file
    ], check=True)

    print(f"Saved stitched file with metadata: {stitched_file}")

def extract_page_from_filename(filename):
    """Return page number as int from filename like _P00_S01.tif"""
    m = re.search(r"_P(\d+)_S\d+\.tif$", filename)
    if m:
        return int(m.group(1))
    return None

if __name__ == "__main__":
    for input_dir in glob.glob(BASE_DIR + "/*_Archive"):
        output_dir = get_view_dirname(input_dir)

        for pair in list_sequential_file_pairs_and_partials(input_dir):
            try:
                page_number = extract_page_from_filename(os.path.basename(pair[0]))

                if len(pair) == 2:
                    stitch(pair, output_dir, book=os.path.basename(input_dir), page=page_number)
                elif len(pair) == 1:
                    tif_to_jpg(pair[0], output_dir, book=os.path.basename(input_dir), page=page_number)
            except Exception as e:
                print("Error processing", pair, e)
