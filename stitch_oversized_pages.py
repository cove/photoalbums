import cv2
import re, os, glob
from stitching import AffineStitcher

HOME = os.environ["HOME"]
BASE_DIR = HOME + "/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"

def get_view_dirname(dir):
    base, ext = os.path.splitext(dir)
    if base.endswith("_Archive"):
        base = base[:-8] + "_View"  # remove '_Archive' and add '_View'
    return base + ext

def list_sequential_file_pairs(directory):
    files = [f for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f)) and re.fullmatch(r'.*[\d+]\.tif', f)]

    def extract_number(filename):
        match = re.search(r'_(\d+)\.tif$', filename)
        return int(match.group(1)) if match else -1

    files.sort(key=extract_number)

    used = set()
    pairs = []

    for i, f1 in enumerate(files):
        if f1 in used:
            continue
        num1 = extract_number(f1)
        for f2 in files[i+1:]:
            if f2 in used:
                continue
            num2 = extract_number(f2)
            if num2 == num1 + 1:
                pairs.append([os.path.join(directory, f1), os.path.join(directory, f2)])
                used.update([f1, f2])
                break

    return pairs

def list_sequential_file_pairs_and_partials(directory):
    files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and re.fullmatch(r'.*\d+\.tif', f)
    ]

    def extract_number(filename):
        match = re.search(r'_(\d+)\.tif$', filename)
        return int(match.group(1)) if match else None

    files.sort(key=lambda f: extract_number(f) if extract_number(f) is not None else float("inf"))

    used = set()
    pairs = []

    for i, f1 in enumerate(files):
        if f1 in used:
            continue

        num1 = extract_number(f1)
        paired = False

        for f2 in files[i + 1:]:
            if f2 in used:
                continue

            num2 = extract_number(f2)
            if num1 is not None and num2 == num1 + 1:
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


def combine_file_names(file1, file2):
    pattern = r'^(.*)_(\d+)(\.\w+)$'  # matches prefix, number, extension
    match1 = re.match(pattern, os.path.basename(file1))
    match2 = re.match(pattern, os.path.basename(file2))

    if not match1 or not match2:
        raise ValueError("Filenames do not match expected pattern.")

    prefix1, num1, ext1 = match1.groups()
    prefix2, num2, ext2 = match2.groups()

    if prefix1 != prefix2 or ext1 != ext2:
        raise ValueError("Files do not have matching prefixes or extensions.")

    combined_name = f"{prefix1}_{num1}-{num2}{ext1}"
    view_combined = combined_name.replace("_Archive_", "_View_")

    return view_combined

def tif_to_jpg(tif_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(tif_path))[0]
    base_name = base_name.replace("Archive", "View")
    jpg_path = os.path.join(output_dir, base_name + ".jpg")

    img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Could not read image: {tif_path}")

    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    cv2.imwrite(jpg_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return jpg_path

def stitch(files, output_dir):
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    output_file = combine_file_names(files[0], files[1])
    base_name = os.path.splitext(output_file)[0]
    jpg_file = base_name + ".jpg"
    final_file = os.path.join(output_dir, jpg_file)

    if os.path.exists(final_file) and os.path.getsize(final_file) > 100_000:
        print(f"Output file already exists. Skipping. {final_file}")
        return

    print("Stitching...", files)

    attempts = [
        {"detector": "sift", "confidence_threshold": 0.4},
        {"detector": "sift", "confidence_threshold": 0.3},
        {"detector": "brisk", "confidence_threshold": 0.2},
        {"detector": "brisk", "confidence_threshold": 0.1},
    ]
    combined = None

    for settings in attempts:
        try:
            print(f"Trying settings: {settings}")
            stitcher = AffineStitcher(**settings)
            combined = stitcher.stitch(files)

            if combined is not None and combined.size > 0:
                break
        except Exception as e:
            print(f"Failed with settings {settings}: {e}")

    if combined is None:
        raise RuntimeError("Stitching failed with all detector settings")

    print(f"Saving stitched file to {final_file}")
    cv2.imwrite(final_file, combined)

if __name__ == '__main__':
    for input_dir in glob.glob(BASE_DIR + "/*_Archive"):
        for pair in list_sequential_file_pairs_and_partials(input_dir):
            output_dir = get_view_dirname(input_dir)
            try:
                if len(pair) == 2:
                    stitch(pair, output_dir)
                elif len(pair) == 1:
                    tif_to_jpg(pair[0], output_dir)
                else:
                    raise ValueError("Invalid pair")
            except Exception as e:
                print(e)
