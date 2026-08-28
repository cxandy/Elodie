#!/usr/bin/env python
"""PyInstaller entry point for the Elodie GUI (frozen executable)."""

from __future__ import print_function
import sys


def main():
    # The GUI detects ExifTool on startup itself (see gui.main_window) and
    # routes the user to the environment-setup page when it is missing, so we
    # do not need to start an ExifTool subprocess here.
    from gui.main import main as gui_main
    gui_main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
