#!/usr/bin/env python3
"""
Extract metadata from image and video files into a TSV.

Extracts XMP, EXIF, and IPTC metadata from .tif, .jpg, .png, and .mp4 files
in a directory tree and exports to TSV, excluding empty fields.
"""

import os
import sys
import subprocess
import json
import csv
from pathlib import Path
from collections import defaultdict

# =====================
# CONFIG
# =====================
if sys.platform.startswith("darwin"):
    HOME = os.environ["HOME"]
    BASE_DIR = f"{HOME}/Library/CloudStorage/OneDrive-Personal/Cordell, Leslie & Audrey/Photo Albums"
elif sys.platform.startswith("win"):
    BASE_DIR = f"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums"
else:
    raise NotImplementedError

# =====================
# METADATA FIELDS TO EXTRACT (EXACT)
# =====================
EXIFTOOL_FIELDS = [
    'IFD0:ImageDescription',

    'XMP-iptcExt:ArtworkContentDescription',

    'XMP-dc:Subject',
    'XMP-dc:Description',
    'XMP-dc:Creator',

    'XMP-photoshop:CaptionWriter',
    'XMP-photoshop:City',
    'XMP-photoshop:State',
    'XMP-photoshop:Country',

    'XMP-iptcCore:Location',
    'XMP-iptcCore:CountryCode',
    'XMP-iptcCore:SubjectCode',
    'XMP-iptcCore:ExtDescrAccessibility',

    'XMP-lr:HierarchicalSubject',

    'IPTC:CodedCharacterSet',
    'IPTC:ApplicationRecordVersion',
    'IPTC:Keywords',
    'IPTC:City',
    'IPTC:Sub-location',
    'IPTC:Province-State',
    'IPTC:Country-PrimaryLocationCode',
    'IPTC:Country-PrimaryLocationName',
    'IPTC:Caption-Abstract',
    'IPTC:Writer-Editor',
]

OUTPUT_FILE = "metadata.tsv"
FILE_EXTENSIONS = ('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.mp4')

# Set to True to include ALL fields (even empty ones) - useful for debugging
INCLUDE_EMPTY_FIELDS = False


def extract_metadata(file_path):
    """Extract all metadata from a file using exiftool"""
    try:
        result = subprocess.run(
            [
                'exiftool',
                '-json',
                '-a',
                '-G1',
                '-struct',
                '-charset', 'UTF8',
                *[f'-{tag}' for tag in EXIFTOOL_FIELDS],
                file_path
            ],
            capture_output=True,
            text=True,
            check=True
        )

        metadata = json.loads(result.stdout)
        if metadata:
            return metadata[0]
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Error reading {file_path}: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing metadata for {file_path}: {e}")
        return {}


def find_files(base_dir, extensions=('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.mp4')):
    """Recursively find all files with specified extensions"""
    files = []
    for root, dirs, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename.lower().endswith(extensions):
                files.append(os.path.join(root, filename))
    return files


def collect_all_metadata(files, progress=True):
    """Collect metadata from all files and track which fields have values"""
    all_metadata = []
    field_has_value = defaultdict(bool)
    keyword_fields_found = set()

    total = len(files)
    for i, file_path in enumerate(files, 1):
        if progress:
            print(f"Processing {i}/{total}: {os.path.basename(file_path)}")

        metadata = extract_metadata(file_path)
        if metadata:
            # Add file path as first column (relative to Photo Albums)
            if "Photo Albums" in file_path:
                relative_path = "Photo Albums" + file_path.split("Photo Albums")[1]
                metadata['FilePath'] = relative_path
            else:
                metadata['FilePath'] = file_path
            all_metadata.append(metadata)

            # Track which fields have non-empty values
            for key, value in metadata.items():
                if value and value != '' and value != [] and value != {}:
                    field_has_value[key] = True
                    # Track keyword-related fields
                    if 'keyword' in key.lower() or 'subject' in key.lower() or 'tag' in key.lower():
                        keyword_fields_found.add(key)

    # Print keyword fields found
    if keyword_fields_found:
        print(f"\nKeyword-related fields found with values:")
        for field in sorted(keyword_fields_found):
            print(f"  - {field}")
    else:
        print("\nWARNING: No keyword-related fields found with values!")
        print("Check if keywords are actually set in your files.")

    return all_metadata, field_has_value


def write_tsv(all_metadata, output_file):
    if not all_metadata:
        print("No metadata found!")
        return

    fields = ['FilePath'] + EXIFTOOL_FIELDS

    print(f"\nWriting {len(all_metadata)} records with {len(fields)} fields to {output_file}")

    with open(output_file, 'w', newline='', encoding='utf-8') as tsvfile:
        writer = csv.DictWriter(tsvfile, fieldnames=fields, delimiter='\t', extrasaction='ignore')
        writer.writeheader()

        for metadata in all_metadata:
            row = {}
            for field in fields:
                value = metadata.get(field, '')
                if isinstance(value, (list, dict)):
                    row[field] = json.dumps(value, ensure_ascii=False)
                else:
                    row[field] = value
            writer.writerow(row)

    print(f"Successfully wrote {output_file}")


def main():
    # Check if exiftool is available
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool is not installed or not in PATH")
        print("Install from: https://exiftool.org/")
        sys.exit(1)

    # Validate directory
    if not os.path.isdir(BASE_DIR):
        print(f"Error: Directory does not exist: {BASE_DIR}")
        sys.exit(1)

    print("=" * 70)
    print("Metadata Extraction Tool")
    print("=" * 70)
    print(f"Directory: {BASE_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Extensions: {', '.join(FILE_EXTENSIONS)}")
    print()

    # Find all files
    print("Scanning for files...")
    files = find_files(BASE_DIR, FILE_EXTENSIONS)
    print(f"Found {len(files)} files")

    if not files:
        print("No files found!")
        sys.exit(0)

    print()

    # Collect metadata
    all_metadata, field_has_value = collect_all_metadata(files, progress=True)

    # Write TSV
    print()
    write_tsv(all_metadata, OUTPUT_FILE)

    print("\n" + "=" * 70)
    print("Complete!")
    print("=" * 70)


if __name__ == '__main__':
    main()