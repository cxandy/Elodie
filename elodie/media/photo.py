"""
The photo module contains the :class:`Photo` class, which is used to track
image objects (JPG, DNG, etc.).

.. moduleauthor:: Jaisen Mathai <jaisen@jmathai.com>
"""
from __future__ import print_function
from __future__ import absolute_import

import os
import re
import time
from datetime import datetime
from re import compile

from PIL import Image

from elodie import log
from .media import Media


class Photo(Media):

    """A photo object.

    :param str source: The fully qualified path to the photo file
    """

    __name__ = 'Photo'

    #: Valid extensions for photo files.
    extensions = ('arw', 'bmp', 'cr2', 'dng', 'gif', 'heic', 'jpeg', 'jpg', 'nef', 'png', 'rw2')

    #: Raw formats that Pillow's built-in decoders cannot open but ExifTool can
    #: read. Used to decide when to fall back to ExifTool in is_valid().
    raw_unsupported_extensions = ('arw', 'cr2', 'nef', 'rw2')

    def __init__(self, source=None):
        super(Photo, self).__init__(source)

        # We only want to parse EXIF once so we store it here
        self.exif = None

        # Use Pillow (required dependency)
        self.pillow = Image

    def get_date_taken(self):
        """Get the date which the photo was taken.

        The date value returned is defined by the min() of mtime and ctime.

        :returns: time object or None for non-photo files or 0 timestamp
        """
        if(not self.is_valid()):
            return None

        source = self.source
        seconds_since_epoch = min(os.path.getmtime(source), os.path.getctime(source))  # noqa

        exif = self.get_exiftool_attributes()
        if not exif:
            return time.gmtime(seconds_since_epoch)

        # We need to parse a string from EXIF into a timestamp.
        # EXIF DateTimeOriginal and EXIF DateTime are both stored
        #   in %Y:%m:%d %H:%M:%S format
        # we split on a space and then r':|-' -> convert to int -> .timetuple()
        #   the conversion in the local timezone
        # EXIF DateTime is already stored as a timestamp
        # Sourced from https://github.com/photo/frontend/blob/master/src/libraries/models/Photo.php#L500  # noqa
        for key in self.exif_map['date_taken']:
            try:
                if(key in exif):
                    if(re.match(r'\d{4}(-|:)\d{2}(-|:)\d{2}', exif[key]) is not None):  # noqa
                        dt, tm = exif[key].split(' ')
                        dt_list = compile(r'-|:').split(dt)
                        dt_list = dt_list + compile(r'-|:').split(tm)
                        dt_list = map(int, dt_list)
                        time_tuple = datetime(*dt_list).timetuple()
                        seconds_since_epoch = time.mktime(time_tuple)
                        break
            except BaseException as e:
                log.error(e)
                pass

        if(seconds_since_epoch == 0):
            # Zero timestamp (iPhone "January 1970 bug"). Try the other
            # filesystem timestamps before giving up so the file can still be
            # imported instead of crashing on date_taken == None.
            try:
                fallback = max(
                    os.path.getmtime(source),
                    os.path.getctime(source),
                    os.path.getatime(source),
                )
                if fallback and fallback > 0:
                    return time.gmtime(fallback)
            except OSError:
                pass
            # No usable timestamp anywhere: fall back to epoch (1970-01-01).
            return time.gmtime(0)

        return time.gmtime(seconds_since_epoch)

    def is_valid(self):
        """Check the file extension against valid file extensions.

        The list of valid file extensions come from self.extensions. This
        also checks whether the file is an image.

        :returns: bool
        """
        source = self.source

        # HEIC is not well supported yet so we special case it.
        # https://github.com/python-pillow/Pillow/issues/2806
        extension = os.path.splitext(source)[1][1:].lower()
        if(extension != 'heic'):
            # gh-4 This checks if the source file is an image, but only as a
            # best effort. Several raw formats (e.g. .arw, .cr2, .nef, .rw2)
            # are not supported by Pillow's built-in decoders even though
            # ExifTool reads them fine. If Pillow cannot identify the file we
            # fall back to ExifTool, but only for those raw formats; a broken
            # JPEG/PNG should still be treated as invalid.
            identified = False
            if(self.pillow is not None):
                try:
                    im = self.pillow.open(source)
                    if(im.format is not None):
                        identified = True
                except IOError:
                    identified = False
            if(not identified and extension in self.raw_unsupported_extensions):
                try:
                    identified = self.get_exiftool_attributes() is not None
                except Exception:
                    identified = False
            if(not identified):
                return False

        return extension in self.extensions
