import os
import glob
import subprocess
from pathlib import Path

HOME = os.environ["HOME"]
BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"


def tiff_needs_conversion(tiff_path: Path) -> bool:
    """
    Check if TIFF has alpha channel or predictor != 2.
    Returns True if conversion is needed.
    """
    try:
        # Use tiffinfo to read metadata
        result = subprocess.run(
            ["tiffinfo", str(tiff_path)],
            capture_output=True,
            text=True,
            check=True
        )
        info = result.stdout.lower()

        # Check for alpha / extra samples
        has_alpha = "extra samples: unassociated alpha" in info or "extra samples: associated alpha" in info

        # Check predictor (default predictor 1 = none)
        predictor_line = [line for line in info.splitlines() if "predictor" in line]
        predictor_ok = any("predictor: 2" in line for line in predictor_line)

        # Needs conversion if alpha exists or predictor not 2
        return has_alpha or not predictor_ok
    except subprocess.CalledProcessError:
        # If tiffinfo fails, assume conversion needed
        return True


def validate_pixels(original_path: Path, converted_path: Path) -> bool:
    """
    Check if two TIFFs are pixel-identical using ImageMagick compare -metric AE.
    Returns True if identical, False otherwise.
    """
    try:
        result = subprocess.run(
            ["magick", "compare", "-metric", "AE", str(original_path), str(converted_path), "null:"],
            capture_output=True,
            text=True,
            check=False  # compare returns 1 if images differ
        )
        # Extract the first number from stderr
        diff_count_str = result.stderr.strip().split()[0]
        diff_count = int(diff_count_str)
        return diff_count == 0
    except Exception as e:
        print(f"Validation error for {original_path}: {e}")
        return False


def process_tiff(input_path: Path, output_path: Path):
    """
    Convert TIFF to remove alpha and apply LZW + predictor=2, preserving metadata,
    then validate that pixels are unchanged.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not tiff_needs_conversion(input_path):
        # Simply copy if already correct
        subprocess.run(["cp", str(input_path), str(output_path)], check=True)
        print(f"Skipped (already correct): {input_path}")
        return

    # Convert with ImageMagick
    cmd = [
        "magick", str(input_path),
        "-alpha", "off",                # Remove alpha channel
        "-compress", "lzw",             # LZW compression
        "-define", "tiff:predictor=2",  # Predictor 2 for better compression
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True)
        # Validate pixels after conversion
        if validate_pixels(input_path, output_path):
            print(f"Processed and validated: {input_path} -> {output_path}")
        else:
            print(f"Pixel mismatch after conversion: {input_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error processing {input_path}: {e}")


def convert_directory(base_dir: str):
    """
    Traverse directories ending with '_Archive', process all TIFFs,
    and save to a mirrored directory ending with '_Compressed'.
    """
    archive_dirs = glob.glob(f"{base_dir}/*_Archive")
    for archive_dir in archive_dirs:
        archive_path = Path(archive_dir)
        output_base = Path(str(archive_path) + "_Compressed")

        # Recursively find all TIFF files
        for tiff_path in archive_path.rglob("*.tif"):
            relative_path = tiff_path.relative_to(archive_path)
            output_path = output_base / relative_path
            process_tiff(tiff_path, output_path)


def main():
    convert_directory(BASE_DIR)


if __name__ == "__main__":
    main()
