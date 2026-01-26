from PIL import Image
import glob
import os, sys

TARGET_W = 5100
TARGET_H = 6746
BASE_DIR = None

if sys.platform.startswith("darwin"):
    HOME = os.environ["HOME"]
    BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums/Eng_1983_B02_Archive"
elif sys.platform.startswith("win"):
    BASE_DIR = f"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums/Eng_1983_B02_Archive"
else:
    raise NotImplementedError


def crop():
    for path in glob.glob("*.tif"):
        if path.endswith("_S01.tif"):
            continue

        with Image.open(path) as img:
            w, h = img.size

            if w < TARGET_W or h < TARGET_H:
                print(f"Skipping {path}: too small ({w}x{h})")
                continue

            left = (w - TARGET_W)
            top = (h - TARGET_H)
            right = left + TARGET_W
            bottom = top + TARGET_H

            cropped = img.crop((left, top, right, bottom))
            cropped.save(path)

            print(f"Cropped {path}")

if '__main__' == __name__:
    crop(BASE_DIR)
