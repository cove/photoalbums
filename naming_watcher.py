import os
import time

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:
    Observer = None

    class FileSystemEventHandler:
        pass

from common import (
    FILENAME_PATTERN,
    INCOMING_NAME,
    PHOTO_ALBUMS_DIR,
    get_next_filename,
    open_image_fullscreen,
    rename_with_retry,
)

WATCH_ROOT = str(PHOTO_ALBUMS_DIR)


class IncomingScanHandler(FileSystemEventHandler):
    def __init__(
        self,
        *,
        get_next_filename_fn=get_next_filename,
        rename_fn=rename_with_retry,
        open_image_fn=open_image_fullscreen,
        sleep_fn=time.sleep,
        incoming_name=INCOMING_NAME,
    ):
        super().__init__()
        self.get_next_filename_fn = get_next_filename_fn
        self.rename_fn = rename_fn
        self.open_image_fn = open_image_fn
        self.sleep_fn = sleep_fn
        self.incoming_name = incoming_name

    def on_created(self, event):
        if event.is_directory:
            return
        if os.path.basename(event.src_path).lower() != self.incoming_name.lower():
            return

        self.sleep_fn(5.0)

        watch_dir = os.path.dirname(event.src_path)
        new_name = self.get_next_filename_fn(watch_dir, FILENAME_PATTERN)
        old_path = os.path.join(watch_dir, self.incoming_name)
        new_path = os.path.join(watch_dir, new_name)

        print(f"Renaming {self.incoming_name} -> {new_name}")
        if not self.rename_fn(old_path, new_path, log_error=print):
            return
        self.open_image_fn(new_path, fallback_to_default=True)


def main() -> None:
    if Observer is None:
        raise RuntimeError("watchdog is required to run this script.")

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
