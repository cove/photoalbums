import glob
import os, subprocess
from wand.image import Image

TARGET_DPI = 600
HOME = os.environ["HOME"]
BASE_DIR = HOME + "/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"

def open_image(path):
    subprocess.run(["open", path])  # macOS
    # Linux: ["xdg-open", path]
    # Windows: ["start", path], shell=True

def rescale_tifs(directory):
    for name in os.listdir(directory):
        if not name.lower().endswith((".tif", ".tiff")):
            continue

        path = os.path.join(directory, name)

        with Image(filename=path) as img:
            xdpi, ydpi = img.resolution

            if xdpi <= TARGET_DPI and ydpi <= TARGET_DPI:
                continue
            else:
                print(f"Would resize {name} to {xdpi}x{ydpi}")

            scale_x = TARGET_DPI / xdpi
            scale_y = TARGET_DPI / ydpi

            new_width = int(img.width * scale_x)
            new_height = int(img.height * scale_y)

            img.filter = "lanczos"
            img.resize(new_width, new_height)

            img.resolution = (TARGET_DPI, TARGET_DPI)
            img.compression = "lzw"

            base, ext = os.path.splitext(path)
            new_path = f"{base}_Resized{ext}"
            img.save(filename=new_path)

            print(f"Rescaled {name}: {xdpi}x{ydpi} -> 600 dpi")

            base, ext = os.path.splitext(path)
            resized_path = f"{base}_Resized{ext}"
            img.save(filename=resized_path)

            print(f"\nOriginal: {path}")
            print(f"Resized : {resized_path}")

            open_image(path)
            open_image(resized_path)

            choice = input("Replace original with resized version? [y/N]: ").strip().lower()

            if choice == "y":
                os.replace(resized_path, path)
                print("Replaced.")
            else:
                os.remove(resized_path)
                print("Kept original.")

if __name__ == "__main__":
    for input_dir in glob.glob(BASE_DIR + "/*_Archive"):
            try:
                rescale_tifs(input_dir)
            except Exception as e:
                print(e)
