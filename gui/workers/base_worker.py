"""Shared QThread base for all GUI workers.

Every worker needs the same cancel flag used by the UI's "Cancel" button.
Subclasses call ``super().__init__()`` and then check ``self.is_cancelled()``
inside their ``run()`` loops.
"""
from PySide6.QtCore import QThread


class BaseWorker(QThread):
    """QThread with a cooperative cancel flag."""

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        """Signal the worker to stop at the next cancellation check."""
        self._cancelled = True

    def is_cancelled(self):
        """Return True once ``cancel()`` has been called."""
        return self._cancelled
