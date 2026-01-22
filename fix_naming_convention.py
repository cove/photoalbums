import re
import os
from pathlib import Path

HOME = os.environ["HOME"]
BASE_DIR = Path(HOME + "/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums")

# CONFIG
INPUT_DIR = BASE_DIR / Path("1986_Audrey_Leslie_Mainland_China_Book_2_Archive")

FILENAME_RE = re.compile(
    r"^(?P<prefix>.+?)_Archive_(?P<seq>\d+)\.tif$",
    re.IGNORECASE
)

# Removes "_Book_1", "_Book_12", etc.
BOOK_RE = re.compile(r"_Book_\d+", re.IGNORECASE)

def do_rename():
    files = []

    for f in INPUT_DIR.iterdir():
        if f.suffix.lower() != ".tif":
            continue

        m = FILENAME_RE.match(f.name)
        if not m:
            continue

        prefix = m.group("prefix")
        prefix = BOOK_RE.sub("", prefix)  # remove Book_<n>

        # Replace Audrey_Leslie with ADC
        prefix = prefix.replace("Audrey_Leslie", "ADC")

        seq = int(m.group("seq"))
        files.append((seq, prefix, f))

    if not files:
        raise RuntimeError("No matching TIFF files found.")

    files.sort(key=lambda x: x[0])

    collection_prefix = files[0][1]
    BASE_NAME = f"{collection_prefix}_B01"

    page_index = 0
    i = 0

    while i < len(files):
        seq, _, file1 = files[i]

        if i + 1 < len(files) and files[i + 1][0] == seq + 1:
            for scan_index, (_, _, f) in enumerate(files[i:i+2], start=1):
                out_name = f"{BASE_NAME}_P{page_index:02d}_S{scan_index:02d}.tif"
                f.rename(f.parent / out_name)
            i += 2
        else:
            out_name = f"{BASE_NAME}_P{page_index:02d}_S01.tif"
            file1.rename(file1.parent / out_name)
            i += 1

        page_index += 1

    print(f"Done. Renamed {page_index} pages.")
    print(f"Base name used: {BASE_NAME}")

if __name__ == "__main__":
    do_rename()
