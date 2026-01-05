import cv2
import re, os, glob
from stitching import AffineStitcher

BASE_DIR="/Users/cove/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"

def get_view_dirname(dir):
    base, ext = os.path.splitext(dir)
    if base.endswith("_Archive"):
        base = base[:-8] + "_View"  # remove '_Archive' and add '_View'
    return base + ext

def list_sequential_file_pairs(directory):
    # List all files
    files = [f for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f)) and re.fullmatch(r'.*[\d+]\.tif', f)]

    def extract_number(filename):
        match = re.search(r'_(\d+)\.tif$', filename)
        return int(match.group(1)) if match else -1

    files.sort(key=extract_number)

    # Keep track of used files
    used = set()
    pairs = []

    for i, f1 in enumerate(files):
        if f1 in used:
            continue
        num1 = extract_number(f1)
        # Look for the next unused sequential file
        for f2 in files[i+1:]:
            if f2 in used:
                continue
            num2 = extract_number(f2)
            if num2 == num1 + 1:
                pairs.append([os.path.join(directory, f1), os.path.join(directory, f2)])
                used.update([f1, f2])
                break  # stop searching for f1 once a pair is found

    return pairs

def combine_file_names(file1, file2):
    # Extract prefix and numbers
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
    return combined_name

def stitch(files, output_dir):

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    output_file = combine_file_names(files[0], files[1])
    base_name = os.path.splitext(output_file)[0]
    jpg_file = base_name + '.jpg'
    final_file = os.path.join(output_dir, jpg_file)

    if os.path.exists(final_file) and os.path.getsize(final_file) > 100_000:
        #print(f"Output file already exists. Skipping. {final_file}")
        return

    print("Stitching...", files)
    settings = {"detector": "brisk", "confidence_threshold": 0.1}
    stitcher = AffineStitcher(**settings)
    combined = stitcher.stitch(files)

    print("Saving stitched file to {}".format(final_file))
    cv2.imwrite(final_file, combined)

if __name__ == '__main__':
    for input_dir in glob.glob(BASE_DIR + "/*_Archive"):
        for pair in list_sequential_file_pairs(input_dir):
            output_dir = get_view_dirname(input_dir)
            try:
                stitch(pair, output_dir)
            except Exception as e:
                print(e)
