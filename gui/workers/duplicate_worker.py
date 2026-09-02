"""Worker thread that scans a directory for duplicate media files."""
import hashlib
import os

from PySide6.QtCore import Signal

from elodie.media.photo import Photo
from elodie.media.video import Video

from gui.workers.base_worker import BaseWorker


class DuplicateWorker(BaseWorker):
    """Scan a directory and group files whose content is identical.

    Files are first bucketed by their byte size; only files sharing a size
    can possibly be duplicates, so the full SHA-256 hash is computed only on
    those candidates. Files whose hashes match are reported as a duplicate
    group (at least two members).

    If ``same_dir_only`` is True, only groups where all files reside in the
    same directory are kept; duplicates across different directories are
    discarded.
    """

    progress = Signal(int, int)  # scanned, total candidates
    status = Signal(str)
    finished = Signal(list)  # list of [hash, [path, ...]], each >= 2 members

    def __init__(self, directory, same_dir_only=False):
        super().__init__()
        self.directory = directory
        self.same_dir_only = same_dir_only

    def run(self):
        extensions = set(Photo.extensions) | set(Video.extensions)
        self.status.emit("正在扫描文件...")

        # Pass 1: collect files with their sizes.
        # When same_dir_only, key by (size, directory) so files in
        # different directories never share a bucket and are never
        # hashed together.  This is the main performance win.
        size_key_to_paths = {}
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
                key = (size, root) if self.same_dir_only else size
                size_key_to_paths.setdefault(key, []).append(path)
                total += 1

        # Candidates: buckets that contain more than one file.
        candidates = [p for paths in size_key_to_paths.values()
                      if len(paths) > 1 for p in paths]
        self.status.emit(f"找到 {total} 个文件，正在计算哈希...")

        # Pass 2: hash only the candidate files that share a key.
        hash_to_paths = {}
        scanned = 0
        for paths in size_key_to_paths.values():
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

        self.finished.emit(self._groups_from(hash_to_paths))

    @classmethod
    def scan(cls, directory, same_dir_only=False):
        """Scans ``directory`` and returns duplicate groups synchronously.

        Each group is ``[hash, [path, ...]]`` with at least two members.
        Files that share no size with any other are skipped to avoid hashing
        every file.

        When ``same_dir_only`` is True, only groups where all files are in
        the same directory are reported; cross-directory duplicates are
        skipped entirely, saving hash computation.
        """
        extensions = set(Photo.extensions) | set(Video.extensions)
        size_key_to_paths = {}
        for root, _dirs, files in os.walk(directory):
            for name in files:
                if os.path.splitext(name)[1][1:].lower() not in extensions:
                    continue
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                key = (size, root) if same_dir_only else size
                size_key_to_paths.setdefault(key, []).append(path)

        hash_to_paths = {}
        for paths in size_key_to_paths.values():
            if len(paths) < 2:
                continue
            for path in paths:
                try:
                    digest = cls._sha256(path)
                except OSError:
                    continue
                if digest:
                    hash_to_paths.setdefault(digest, []).append(path)

        return cls._groups_from(hash_to_paths)

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

    @staticmethod
    def _groups_from(hash_to_paths, same_dir_only=False):
        groups = [
            [digest, paths]
            for digest, paths in hash_to_paths.items()
            if len(paths) >= 2
        ]
        if same_dir_only:
            groups = [
                [digest, paths]
                for digest, paths in groups
                if len(set(os.path.dirname(p) for p in paths)) == 1
            ]
        return groups
