"""Shared utility functions for the GUI."""
import os

from elodie.external.pyexiftool import ExifTool
from elodie import constants
from elodie.dependencies import get_exiftool


def get_exiftool_instance():
    """Get an ExifTool instance with the correct config."""
    exiftool_addedargs = [
        u'-config',
        u'"{}"'.format(constants.exiftool_config)
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
    for category, extensions in SUPPORTED_EXTENSIONS.items():
        if ext in extensions:
            return True
    return False
