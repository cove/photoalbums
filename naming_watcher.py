import os
import re
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

# Watch all book directories under this root.
WATCH_ROOT = r"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums"
INCOMING_NAME = "incoming_scan.tif"

# Regex to match filenames like: Europe_1973_Bxx_P05_S02.tif
FILENAME_PATTERN = re.compile(
    r"^(?P<prefix>.+)_P(?P<page>\d{2})_S(?P<scan>\d{2})\.tif$", re.IGNORECASE
)

def open_image_fullscreen(path):
    # Adjust if your install path is different
    xnview = r"C:\Program Files\XnViewMP\xnviewmp.exe"

    if os.path.exists(xnview):
        subprocess.Popen([xnview, path])
    else:
        # fallback to default viewer
        os.startfile(path)

def derive_prefix(dir_path):
    base = os.path.basename(dir_path)
    if base.lower().endswith("_archive"):
        base = base[: -len("_archive")]
    return base


def get_next_filename(watch_dir):
    """Determine the next filename based on existing files in the directory."""
    files = [f for f in os.listdir(watch_dir) if f.lower().endswith(".tif")]

    # Filter only files matching the naming pattern
    valid_files = []
    for f in files:
        match = FILENAME_PATTERN.match(f)
        if match:
            valid_files.append(f)

    if not valid_files:
        # No files yet - start with cover (page 01, scan 01)
        prefix = derive_prefix(watch_dir)
        return f"{prefix}_P01_S01.tif"

    # Sort alphabetically (works because numbers are zero-padded)
    valid_files.sort()
    last_file = valid_files[-1]

    match = FILENAME_PATTERN.match(last_file)
    prefix = match.group("prefix")
    page = int(match.group("page"))
    scan = int(match.group("scan"))

    # Determine next scan/page (cover is single scan P01_S01)
    if page == 1:
        page = 2
        scan = 1
    else:
        if scan < 2:
            scan += 1
        else:
            page += 1
            scan = 1

    new_filename = f"{prefix}_P{page:02d}_S{scan:02d}.tif"
    return new_filename


class IncomingScanHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Trigger only when incoming_scan.tif appears
        if event.is_directory:
            return
        if os.path.basename(event.src_path).lower() == INCOMING_NAME.lower():
            time.sleep(5.0)  # slight delay to ensure file is fully written

            watch_dir = os.path.dirname(event.src_path)
            new_name = get_next_filename(watch_dir)
            old_path = os.path.join(watch_dir, INCOMING_NAME)
            new_path = os.path.join(watch_dir, new_name)

            print(f"Renaming {INCOMING_NAME} -> {new_name}")
            os.rename(old_path, new_path)
            open_image_fullscreen(new_path)


def main():
    print(f"Watching for {INCOMING_NAME} in:")
    print(WATCH_ROOT)

    event_handler = IncomingScanHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_ROOT, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()


