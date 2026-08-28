"""Worker thread for import operations."""
import os
import threading

from PySide6.QtCore import QThread, Signal

from elodie.compatability import _decode
from elodie.dependencies import get_exiftool
from elodie.filesystem import FileSystem
from elodie.media.base import get_all_subclasses
from elodie.media.media import Media
# Importing the concrete media subclasses registers them so that
# get_all_subclasses() returns them and Media.get_class_by_file()
# can recognize files. Without these imports every file is treated
# as having no media class and silently skipped.
from elodie.media.photo import Photo  # noqa: F401
from elodie.media.video import Video  # noqa: F401
from elodie.media.audio import Audio  # noqa: F401
from elodie.media.text import Text  # noqa: F401

FILESYSTEM = FileSystem()


class ImportWorker(QThread):
    """Worker thread that imports files without blocking the UI."""

    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(list)  # list of (source, dest, success)
    error = Signal(str)
    confirm = Signal(str, str)  # message, filepath

    def __init__(self, files, destination, album_from_folder=False,
                 trash=False, allow_duplicates=False, move=False,
                 location=None, time=None):
        super().__init__()
        self.files = files
        self.destination = destination
        self.album_from_folder = album_from_folder
        self.trash = trash
        self.allow_duplicates = allow_duplicates
        self.move = move
        self.location = location
        self.time = time
        self._cancelled = False
        self._confirm_event = threading.Event()
        self._confirm_result = False

    def cancel(self):
        self._cancelled = True

    def request_confirm(self, message, filepath):
        """Emit confirm signal and block until GUI responds."""
        self._confirm_result = False
        self._confirm_event.clear()
        self.confirm.emit(message, filepath)
        self._confirm_event.wait()
        return self._confirm_result

    def set_confirm_result(self, result):
        """Called by GUI thread to deliver the user's choice."""
        self._confirm_result = result
        self._confirm_event.set()

    def run(self):
        from elodie import geolocation
        from send2trash import send2trash as _send2trash

        results = []
        total = len(self.files)

        if not get_exiftool():
            for filepath in self.files:
                results.append((filepath, None, False))
            self.finished.emit(results)
            return

        for i, filepath in enumerate(self.files):
            if self._cancelled:
                break
            filepath = _decode(filepath)
            self.progress.emit(i + 1, total, os.path.basename(filepath))

            try:
                if not os.path.exists(filepath):
                    results.append((filepath, None, False))
                    continue

                media = Media.get_class_by_file(filepath, get_all_subclasses())
                if not media:
                    results.append((filepath, None, False))
                    continue

                if self.album_from_folder:
                    media.set_album_from_folder()

                if self.location:
                    location_coords = geolocation.coordinates_by_name(self.location)
                    if location_coords and 'latitude' in location_coords and 'longitude' in location_coords:
                        media.set_location(
                            location_coords['latitude'],
                            location_coords['longitude']
                        )

                if self.time:
                    import re
                    from datetime import datetime
                    time_string = self.time
                    time_format = '%Y-%m-%d %H:%M:%S'
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', time_string):
                        time_string = '%s 00:00:00' % time_string
                    dt = datetime.strptime(time_string, time_format)
                    media.set_date_taken(dt)

                if self.move:
                    metadata = media.get_metadata()
                    folder_path = FILESYSTEM.get_folder_path(metadata)
                    file_name = FILESYSTEM.get_file_name(metadata)
                    final_dest = os.path.join(
                        self.destination, folder_path, file_name
                    )
                    if os.path.exists(final_dest):
                        msg = (
                            f"目标文件已存在:\n{final_dest}\n\n"
                            f"源文件: {filepath}\n\n"
                            f"是否覆盖？"
                        )
                        confirmed = self.request_confirm(msg, filepath)
                        if not confirmed:
                            results.append((filepath, final_dest, False))
                            continue

                dest_path = FILESYSTEM.process_file(
                    filepath, self.destination, media,
                    allowDuplicate=self.allow_duplicates,
                    move=self.move
                )

                if dest_path:
                    results.append((filepath, dest_path, True))
                    if self.trash and not self.move:
                        _send2trash(filepath)
                else:
                    results.append((filepath, None, False))

            except Exception as e:
                results.append((filepath, None, False))
                self.progress.emit(i + 1, total,
                                   f"[错误] {os.path.basename(filepath)}: {e}")

        self.finished.emit(results)


class UpdateWorker(QThread):
    """Worker thread that updates file metadata without blocking the UI."""

    progress = Signal(int, int, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, files, location=None, time=None,
                 album=None, title=None):
        super().__init__()
        self.files = files
        self.location = location
        self.time = time
        self.album = album
        self.title = title
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from elodie import geolocation
        import re
        from datetime import datetime

        results = []
        total = len(self.files)

        if not get_exiftool():
            for filepath in self.files:
                results.append((filepath, None, False))
            self.finished.emit(results)
            return

        for i, filepath in enumerate(self.files):
            if self._cancelled:
                break
            filepath = _decode(filepath)
            self.progress.emit(i + 1, total, os.path.basename(filepath))

            try:
                if not os.path.exists(filepath):
                    results.append((filepath, None, False))
                    continue

                media = Media.get_class_by_file(filepath, get_all_subclasses())
                if not media:
                    results.append((filepath, None, False))
                    continue

                updated = False
                if self.location:
                    location_coords = geolocation.coordinates_by_name(self.location)
                    if location_coords and 'latitude' in location_coords:
                        media.set_location(
                            location_coords['latitude'],
                            location_coords['longitude']
                        )
                        updated = True

                if self.time:
                    time_string = self.time
                    time_format = '%Y-%m-%d %H:%M:%S'
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', time_string):
                        time_string = '%s 00:00:00' % time_string
                    dt = datetime.strptime(time_string, time_format)
                    media.set_date_taken(dt)
                    updated = True

                if self.album:
                    media.set_album(self.album)
                    updated = True

                if self.title:
                    media.set_title(self.title)
                    updated = True

                if updated:
                    current_directory = os.path.dirname(filepath)
                    destination_depth = -1 * len(FILESYSTEM.get_folder_path_definition())
                    destination = os.sep.join(
                        os.path.normpath(current_directory).split(os.sep)[:destination_depth]
                    )
                    dest_path = FILESYSTEM.process_file(
                        filepath, destination, media,
                        move=True, allowDuplicate=True
                    )
                    FILESYSTEM.delete_directory_if_empty(os.path.dirname(filepath))
                    results.append((filepath, dest_path, bool(dest_path)))
                else:
                    results.append((filepath, None, False))

            except Exception as e:
                results.append((filepath, None, False))
                self.progress.emit(i + 1, total,
                                   f"[错误] {os.path.basename(filepath)}: {e}")

        self.finished.emit(results)
