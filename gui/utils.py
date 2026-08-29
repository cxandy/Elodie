"""Shared utility functions for the GUI."""
import os

from elodie import constants
from elodie.dependencies import get_exiftool
from elodie.external.pyexiftool import ExifTool


def get_exiftool_instance():
    """Get an ExifTool instance with the correct config."""
    exiftool_addedargs = [
        '-config',
        f'"{constants.exiftool_config}"'
    ]
    return ExifTool(
        executable_=get_exiftool(),
        addedargs=exiftool_addedargs
    )


SUPPORTED_EXTENSIONS = {
    'photo': ('arw', 'cr2', 'dng', 'gif', 'heic', 'jpeg', 'jpg', 'nef', 'png', 'rw2'),
    'video': ('3gp', 'avi', 'mov', 'mp4', 'mpg', 'mpeg', 'mts', 'm2ts'),
    'audio': ('m4a',),
    'text': ('txt',),
}


def is_supported_file(filepath):
    """Check if a file is a supported media type."""
    ext = os.path.splitext(filepath)[1][1:].lower()
    return any(ext in extensions for extensions in SUPPORTED_EXTENSIONS.values())
