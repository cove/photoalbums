import os, re, glob, subprocess, sys

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

def parse_filename(filename):
    m = FILENAME_RE.search(filename)
    if not m:
        return ("Unknown", "Unknown", "00", "00")
    return m.group("collection"), m.group("year"), m.group("book"), m.group("page")


def count_totals(archive_dirs):
    """Count total pages and scans per page for each collection/book.
       If counted unique pages != highest page number, use highest page number.
    """
    totals = {}

    for archive in archive_dirs:
        files = [f for f in os.listdir(archive) if NEW_NAME_RE.fullmatch(f)]

        for f in files:
            collection, year, book, page = parse_filename(f)
            key = f"{collection}_{year}_B{book}"

            if key not in totals:
                totals[key] = {
                    "pages": set(),
                    "page_scans": {},
                    "max_page": 0
                }

            m = re.search(r"_P(\d+)_S(\d+)", f)
            if m:
                page_num = int(m.group(1))
                scan_num = int(m.group(2))

                totals[key]["pages"].add(page_num)
                totals[key]["max_page"] = max(totals[key]["max_page"], page_num)

                if page_num not in totals[key]["page_scans"]:
                    totals[key]["page_scans"][page_num] = 0
                totals[key]["page_scans"][page_num] = max(
                    totals[key]["page_scans"][page_num],
                    scan_num
                )

    # Finalize total_pages
    for key in totals:
        unique_count = len(totals[key]["pages"])
        highest_page = totals[key]["max_page"]

        if unique_count != highest_page:
            totals[key]["total_pages"] = highest_page
        else:
            totals[key]["total_pages"] = unique_count

        del totals[key]["pages"]
        del totals[key]["max_page"]

    return totals


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


def file_modified_ts(p: str) -> float:
    return float(os.path.getmtime(p))


# =====================
# MAIN
# =====================
if __name__ == "__main__":
    updated = skipped = failures = 0

    # Get all archive directories
    archive_dirs = glob.glob(f"{BASE_DIR}/*_Archive")

    # Count totals across all archives
    print("Counting total pages and scans per book...")
    totals = count_totals(archive_dirs)

    for key, data in totals.items():
        total_scans = sum(data["page_scans"].values())
        print(f"{key}: {data['total_pages']} pages, {total_scans} total scans")
    print()

    all_tifs = []
    for archive in archive_dirs:
        for f in os.listdir(archive):
            if NEW_NAME_RE.fullmatch(f):
                all_tifs.append(os.path.join(archive, f))

    all_tifs.sort(key=file_modified_ts, reverse=True)

    for tif_path in all_tifs:
        f = os.path.basename(tif_path)
        collection, year, book, page = parse_filename(f)
        key = f"{collection}_{year}_B{book}"
        total_pages = totals.get(key, {}).get("total_pages", 0)
        page_num = int(page)
        total_scans_for_page = totals.get(key, {}).get("page_scans", {}).get(page_num, 1)

        m = re.search(r"_S(\d+)", f)
        scan_num = int(m.group(1)) if m else 1

        tif_book_display = book if book == "∅" else f"{int(book):02d}"
        header = (
            f"{collection} ({year}) - Book {tif_book_display}, "
            f"Page {int(page):02d} of {total_pages:02d}, "
            f"Scan S{scan_num:02d} of {total_scans_for_page} total"
        )

        try:
            if update_tif_metadata(tif_path, header):
                print(f"Updated TIFF metadata for {os.path.basename(tif_path)}")
                updated += 1
            else:
                print(f"TIFF metadata already current for {os.path.basename(tif_path)}")
                skipped += 1
        except Exception as e:
            failures += 1
            print(f"Warning: Could not update TIFF metadata for {os.path.basename(tif_path)}: {e}")

    print("\n===== SUMMARY =====")
    print("Updated:", updated)
    print("Skipped:", skipped)
    print("Failed:", failures)
