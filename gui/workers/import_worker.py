"""Worker thread for import operations."""
import os
import traceback

from PySide6.QtCore import QThread, Signal

from elodie import constants
from elodie.compatability import _decode
from elodie.config import load_config
from elodie.filesystem import FileSystem
from elodie.media.base import Base, get_all_subclasses
from elodie.media.media import Media
from elodie.media.text import Text
from elodie.media.audio import Audio
from elodie.media.photo import Photo
from elodie.media.video import Video
from elodie.external.pyexiftool import ExifTool
from elodie.dependencies import get_exiftool

FILESYSTEM = FileSystem()


class ImportWorker(QThread):
    """Worker thread that imports files without blocking the UI."""

    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(list)  # list of (source, dest, success)
    error = Signal(str)

    def __init__(self, files, destination, album_from_folder=False,
                 trash=False, allow_duplicates=False,
                 location=None, time=None):
        super().__init__()
        self.files = files
        self.destination = destination
        self.album_from_folder = album_from_folder
        self.trash = trash
        self.allow_duplicates = allow_duplicates
        self.location = location
        self.time = time

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

        exiftool_addedargs = [
            u'-config',
            u'"{}"'.format(constants.exiftool_config)
        ]

        with ExifTool(executable_=get_exiftool(), addedargs=exiftool_addedargs):
            for i, filepath in enumerate(self.files):
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

                    dest_path = FILESYSTEM.process_file(
                        filepath, self.destination, media,
                        allowDuplicate=self.allow_duplicates, move=False
                    )

                    if dest_path:
                        results.append((filepath, dest_path, True))
                        if self.trash:
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

        exiftool_addedargs = [
            u'-config',
            u'"{}"'.format(constants.exiftool_config)
        ]

        with ExifTool(executable_=get_exiftool(), addedargs=exiftool_addedargs):
            for i, filepath in enumerate(self.files):
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
