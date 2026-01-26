import os
import re
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

WATCH_DIR = r"C:/Users/covec/OneDrive/Cordell, Leslie & Audrey/Photo Albums/Europe_1973_Bxx_Archive"
INCOMING_NAME = "incoming_scan.tif"

# Regex to match filenames like: Europe_1973_Bxx_P05_S02.tif
FILENAME_PATTERN = re.compile(
    r"^(?P<prefix>.+_B..)_P(?P<page>\d{2})_S(?P<scan>\d{2})\.tif$", re.IGNORECASE
)

def open_image_fullscreen(path):
    # Adjust if your install path is different
    xnview = r"C:\Program Files\XnViewMP\xnviewmp.exe"

    if os.path.exists(xnview):
        subprocess.Popen([xnview, path])
    else:
        # fallback to default viewer
        os.startfile(path)

def get_next_filename():
    """Determine the next filename based on existing files in the directory."""
    files = [f for f in os.listdir(WATCH_DIR) if f.lower().endswith(".tif")]

    # Filter only files matching the naming pattern
    valid_files = []
    for f in files:
        match = FILENAME_PATTERN.match(f)
        if match:
            valid_files.append(f)

    if not valid_files:
        # No files yet — start at page 01, scan 01
        return "Europe_1973_Bxx_P01_S01.tif"

    # Sort alphabetically (works because numbers are zero-padded)
    valid_files.sort()
    last_file = valid_files[-1]

    match = FILENAME_PATTERN.match(last_file)
    prefix = match.group("prefix")
    page = int(match.group("page"))
    scan = int(match.group("scan"))

    # Determine next scan/page
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
        if os.path.basename(event.src_path).lower() == INCOMING_NAME.lower():
            time.sleep(0.2)  # slight delay to ensure file is fully written

            new_name = get_next_filename()
            old_path = os.path.join(WATCH_DIR, INCOMING_NAME)
            new_path = os.path.join(WATCH_DIR, new_name)

            print(f"Renaming {INCOMING_NAME} → {new_name}")
            os.rename(old_path, new_path)
            open_image_fullscreen(new_path)


def main():
    print(f"Watching for {INCOMING_NAME} in:")
    print(WATCH_DIR)

    event_handler = IncomingScanHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
