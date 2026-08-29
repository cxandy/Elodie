"""Worker thread that scans a directory for duplicate media files."""
import hashlib
import os

from PySide6.QtCore import QThread, Signal

from elodie.media.photo import Photo
from elodie.media.video import Video


class DuplicateWorker(QThread):
    """Scan a directory and group files whose content is identical.

    Files are first bucketed by their byte size; only files sharing a size
    can possibly be duplicates, so the full SHA-256 hash is computed only on
    those candidates. Files whose hashes match are reported as a duplicate
    group (at least two members).
    """

    progress = Signal(int, int)  # scanned, total candidates
    status = Signal(str)
    finished = Signal(list)  # list of [hash, [path, ...]], each >= 2 members

    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        extensions = set(Photo.extensions) | set(Video.extensions)

        # Pass 1: collect files with their sizes.
        size_to_paths = {}
        total = 0
        for root, _dirs, files in os.walk(self.directory):
            for name in files:
                if self._cancelled:
                    self.finished.emit([])
                    return
                if os.path.splitext(name)[1][1:].lower() not in extensions:
                    continue
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                size_to_paths.setdefault(size, []).append(path)
                total += 1

        # Candidates: sizes that occur more than once.
        candidates = [p for paths in size_to_paths.values()
                      if len(paths) > 1 for p in paths]

        # Pass 2: hash only the candidate files that share a size.
        hash_to_paths = {}
        scanned = 0
        for paths in size_to_paths.values():
            if len(paths) < 2:
                continue
            for path in paths:
                if self._cancelled:
                    self.finished.emit([])
                    return
                try:
                    digest = self._sha256(path)
                except OSError:
                    continue
                if digest:
                    hash_to_paths.setdefault(digest, []).append(path)
                scanned += 1
                self.progress.emit(scanned, len(candidates))

        groups = [
            [digest, paths]
            for digest, paths in hash_to_paths.items()
            if len(paths) >= 2
        ]
        self.finished.emit(groups)

    @classmethod
    def scan(cls, directory):
        """Scans ``directory`` and returns duplicate groups synchronously.

        Each group is ``[hash, [path, ...]]`` with at least two members.
        Files that share no size with any other are skipped to avoid hashing
        every file.
        """
        extensions = set(Photo.extensions) | set(Video.extensions)
        size_to_paths = {}
        for root, _dirs, files in os.walk(directory):
            for name in files:
                if os.path.splitext(name)[1][1:].lower() not in extensions:
                    continue
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                size_to_paths.setdefault(size, []).append(path)

        hash_to_paths = {}
        for paths in size_to_paths.values():
            if len(paths) < 2:
                continue
            for path in paths:
                try:
                    digest = cls._sha256(path)
                except OSError:
                    continue
                if digest:
                    hash_to_paths.setdefault(digest, []).append(path)

        return [
            [digest, paths]
            for digest, paths in hash_to_paths.items()
            if len(paths) >= 2
        ]

    @staticmethod
    def _sha256(path, blocksize=65536):
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                buf = f.read(blocksize)
                if not buf:
                    break
                hasher.update(buf)
        return hasher.hexdigest()
