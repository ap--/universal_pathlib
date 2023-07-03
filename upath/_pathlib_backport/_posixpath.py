import os
import sys
import warnings
from posixpath import sep
from posixpath import altsep
from posixpath import join
from posixpath import splitdrive
from posixpath import normcase
from posixpath import isabs
from posixpath import ismount
from posixpath import samestat
from posixpath import abspath
from posixpath import expanduser
from posixpath import realpath as _realpath


__all__ = [
    "sep",
    "altsep",
    "splitroot",
    "join",
    "splitdrive",
    "normcase",
    "isabs",
    "ismount",
    "isjunction",
    "samestat",
    "abspath",
    "realpath",
    "expanduser",
]


if sys.version_info >= (3, 10):
    realpath = _realpath

else:
    def realpath(path, *, strict=False):
        if strict is not False:
            warnings.warn(
                f"posixpath.realpath(pth) `strict` keyword is ignored on python {sys.version}",
                stacklevel=2,
            )
        return _realpath(path)


def splitroot(p):
    """Split a pathname into drive, root and tail. On Posix, drive is always
    empty; the root may be empty, a single slash, or two slashes. The tail
    contains anything after the root. For example:

        splitroot('foo/bar') == ('', '', 'foo/bar')
        splitroot('/foo/bar') == ('', '/', 'foo/bar')
        splitroot('//foo/bar') == ('', '//', 'foo/bar')
        splitroot('///foo/bar') == ('', '/', '//foo/bar')
    """
    p = os.fspath(p)
    if isinstance(p, bytes):
        sep = b'/'
        empty = b''
    else:
        sep = '/'
        empty = ''
    if p[:1] != sep:
        # Relative path, e.g.: 'foo'
        return empty, empty, p
    elif p[1:2] != sep or p[2:3] == sep:
        # Absolute path, e.g.: '/foo', '///foo', '////foo', etc.
        return empty, sep, p[1:]
    else:
        # Precisely two leading slashes, e.g.: '//foo'. Implementation defined per POSIX, see
        # https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap04.html#tag_04_13
        return empty, p[:2], p[2:]


def isjunction(path):
    """Test whether a path is a junction"""
    return False
