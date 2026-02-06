import os
import subprocess
import sys
from pathlib import Path

from wand.image import Image

from common import PHOTO_ALBUMS_DIR, list_archive_dirs

TARGET_DPI = 600
REVIEW_LOG_PATH = PHOTO_ALBUMS_DIR / "reviewed_tifs.txt"


def open_image(path: Path) -> None:
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        os.startfile(str(path))
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def load_reviewed() -> set[str]:
    if not REVIEW_LOG_PATH.exists():
        return set()
    return set(REVIEW_LOG_PATH.read_text(encoding="utf-8").splitlines())


def mark_reviewed(filename: str) -> None:
    with REVIEW_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(filename + "\n")


def rescale_tifs(directory: Path) -> None:
    reviewed = load_reviewed()

    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in {".tif", ".tiff"}:
            continue
        if entry.name in reviewed:
            continue

        with Image(filename=str(entry)) as img:
            xdpi, ydpi = img.resolution

            if xdpi <= TARGET_DPI and ydpi <= TARGET_DPI:
                mark_reviewed(entry.name)
                continue

            scale_x = TARGET_DPI / xdpi
            scale_y = TARGET_DPI / ydpi

            new_width = int(img.width * scale_x)
            new_height = int(img.height * scale_y)

            img.filter = "lanczos"
            img.resize(new_width, new_height)
            img.resolution = (TARGET_DPI, TARGET_DPI)
            img.compression = "lzw"

            resized_path = entry.with_name(f"{entry.stem}_Resized{entry.suffix}")
            img.save(filename=str(resized_path))

        print(f"\nOriginal: {entry}")
        print(f"Resized : {resized_path}")

        open_image(entry)
        open_image(resized_path)

        choice = input("Replace original with resized version? [y/N]: ").strip().lower()

        if choice == "y":
            resized_path.replace(entry)
            print("Replaced.")
        else:
            resized_path.unlink(missing_ok=True)
            print("Kept original.")

        mark_reviewed(entry.name)


def main() -> None:
    for input_dir in list_archive_dirs(PHOTO_ALBUMS_DIR):
        try:
            rescale_tifs(input_dir)
        except Exception as exc:
            print(exc)


if __name__ == "__main__":
    main()
