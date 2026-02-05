import os, re, glob, sys
import warnings
import cv2
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


NEW_NAME_RE = re.compile(
    r"^[A-Z]{2,}_\d{4}(?:-\d{4})?_B\d{2}_P\d{2}_S\d{2}\.tif$",
    re.IGNORECASE
)

FILENAME_RE = re.compile(
    r"(?P<collection>[A-Z]+)_(?P<year>\d{4}(?:-\d{4})?)_B(?P<book>\d{2})_P(?P<page>\d+)_S\d+",
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
# VALIDATION
# =====================
def validate_single(tif_path):
    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Could not read image")

    if img.ndim == 2:
        _ = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        _ = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def validate_stitch(files):
    print("Validating stitch:", [os.path.basename(f) for f in files])

    attempts = [
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.1},
    ]

    result = None
    partial_warning = None
    for cfg in attempts:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = AffineStitcher(**cfg).stitch(files)
            partial_warning = next(
                (
                    w
                    for w in caught
                    if "not all images are included in the final panorama"
                    in str(w.message).lower()
                ),
                None,
            )
            if partial_warning is not None:
                result = None
                continue
            if result is not None and result.size:
                break
        except Exception:
            pass

    if result is None:
        if partial_warning is not None:
            raise RuntimeError(
                "Stitching produced a partial panorama (not all scans were included)"
            )
        raise RuntimeError("All stitching attempts failed")

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


def file_created_ts(p: str) -> float:
    return dir_created_ts(p)

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    success = failures = 0
    failed = []

    # Get all archive directories
    archive_dirs = glob.glob(f"{BASE_DIR}/*_Archive")

    archive_dirs.sort(key=dir_created_ts, reverse=True)

    # Count totals across all archives
    print("Counting total pages and scans per book...")
    totals = count_totals(archive_dirs)

    for key, data in totals.items():
        total_scans = sum(data['page_scans'].values())
        print(f"{key}: {data['total_pages']} pages, {total_scans} total scans")
    print()

    for archive in archive_dirs:
        groups = list_page_scans(archive)
        groups.sort(
            key=lambda g: max(file_created_ts(p) for p in g),
            reverse=True
        )

        for group in groups:
            try:
                if len(group) > 1:
                    validate_stitch(group)
                else:
                    validate_single(group[0])
                success += 1
            except Exception as e:
                failures += 1
                failed.append(group)
                print("Error:", e)

    print("\n===== SUMMARY =====")
    print("Processed:", success + failures)
    print("Successful:", success)
    print("Failed:", failures)
    for f in failed:
        print(" -", ", ".join(os.path.basename(x) for x in f))
