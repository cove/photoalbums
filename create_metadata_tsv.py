#!/usr/bin/env python3
"""
Extract metadata from image and video files into a TSV.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

from common import PHOTO_ALBUMS_DIR

EXIFTOOL_FIELDS = [
    "IFD0:ImageDescription",
    "XMP-iptcExt:ArtworkContentDescription",
    "XMP-dc:Subject",
    "XMP-dc:Description",
    "XMP-dc:Creator",
    "XMP-photoshop:CaptionWriter",
    "XMP-photoshop:City",
    "XMP-photoshop:State",
    "XMP-photoshop:Country",
    "XMP-iptcCore:Location",
    "XMP-iptcCore:CountryCode",
    "XMP-iptcCore:SubjectCode",
    "XMP-iptcCore:ExtDescrAccessibility",
    "XMP-lr:HierarchicalSubject",
    "IPTC:CodedCharacterSet",
    "IPTC:ApplicationRecordVersion",
    "IPTC:Keywords",
    "IPTC:City",
    "IPTC:Sub-location",
    "IPTC:Province-State",
    "IPTC:Country-PrimaryLocationCode",
    "IPTC:Country-PrimaryLocationName",
    "IPTC:Caption-Abstract",
    "IPTC:Writer-Editor",
]

OUTPUT_FILE = "metadata.tsv"
FILE_EXTENSIONS = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".mp4"}


def extract_metadata(file_path: Path) -> dict:
    try:
        result = subprocess.run(
            [
                "exiftool",
                "-json",
                "-a",
                "-G1",
                "-struct",
                "-charset",
                "UTF8",
                *[f"-{tag}" for tag in EXIFTOOL_FIELDS],
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        metadata = json.loads(result.stdout)
        return metadata[0] if metadata else {}
    except subprocess.CalledProcessError as exc:
        print(f"Error reading {file_path}: {exc}")
        return {}
    except json.JSONDecodeError as exc:
        print(f"Error parsing metadata for {file_path}: {exc}")
        return {}


def find_files(base_dir: Path, extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in base_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            files.append(path)
    return files


def collect_all_metadata(files: list[Path], progress: bool = True) -> list[dict]:
    all_metadata = []
    keyword_fields_found = set()

    total = len(files)
    for idx, file_path in enumerate(files, 1):
        if progress:
            print(f"Processing {idx}/{total}: {file_path.name}")

        metadata = extract_metadata(file_path)
        if not metadata:
            continue

        try:
            rel_path = file_path.relative_to(PHOTO_ALBUMS_DIR)
            metadata["FilePath"] = str(Path("Photo Albums") / rel_path)
        except ValueError:
            metadata["FilePath"] = str(file_path)

        all_metadata.append(metadata)

        for key, value in metadata.items():
            if value not in ("", None, [], {}):
                if "keyword" in key.lower() or "subject" in key.lower() or "tag" in key.lower():
                    keyword_fields_found.add(key)

    if keyword_fields_found:
        print("\nKeyword-related fields found with values:")
        for field in sorted(keyword_fields_found):
            print(f"  - {field}")
    else:
        print("\nWARNING: No keyword-related fields found with values!")
        print("Check if keywords are actually set in your files.")

    return all_metadata


def write_tsv(all_metadata: list[dict], output_file: str) -> None:
    if not all_metadata:
        print("No metadata found!")
        return

    fields = ["FilePath"] + EXIFTOOL_FIELDS

    print(f"\nWriting {len(all_metadata)} records with {len(fields)} fields to {output_file}")

    with open(output_file, "w", newline="", encoding="utf-8") as tsvfile:
        writer = csv.DictWriter(tsvfile, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()

        for metadata in all_metadata:
            row = {}
            for field in fields:
                value = metadata.get(field, "")
                if isinstance(value, (list, dict)):
                    row[field] = json.dumps(value, ensure_ascii=False)
                else:
                    row[field] = value
            writer.writerow(row)

    print(f"Successfully wrote {output_file}")


def main() -> None:
    try:
        subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool is not installed or not in PATH")
        print("Install from: https://exiftool.org/")
        sys.exit(1)

    if not PHOTO_ALBUMS_DIR.is_dir():
        print(f"Error: Directory does not exist: {PHOTO_ALBUMS_DIR}")
        sys.exit(1)

    print("=" * 70)
    print("Metadata Extraction Tool")
    print("=" * 70)
    print(f"Directory: {PHOTO_ALBUMS_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Extensions: {', '.join(sorted(FILE_EXTENSIONS))}")
    print()

    print("Scanning for files...")
    files = find_files(PHOTO_ALBUMS_DIR, FILE_EXTENSIONS)
    print(f"Found {len(files)} files")

    if not files:
        print("No files found!")
        sys.exit(0)

    print()

    all_metadata = collect_all_metadata(files, progress=True)

    print()
    write_tsv(all_metadata, OUTPUT_FILE)

    print("\n" + "=" * 70)
    print("Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
