from __future__ import annotations

import os
import sys

from upath._flavour import fsspecpath

if sys.version_info >= (3, 12):
    from pathlib import Path
    from pathlib import PosixPath
    from pathlib import PurePath
    from pathlib import WindowsPath

else:
    from upath._pathlib_backport import Path
    from upath._pathlib_backport import PosixPath
    from upath._pathlib_backport import PurePath
    from upath._pathlib_backport import WindowsPath


__all__ = [
    "UPath",
]


class PureFSSpecPath(PurePath):
    _flavour = fsspecpath
    __slots__ = ()


class UPath(Path):
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        if cls is UPath:
            cls = WindowsUPath if os.name == "nt" else PosixUPath
        return object.__new__(cls)


class PosixUPath(UPath, PosixPath):
    __slots__ = ()


class WindowsUPath(UPath, WindowsPath):
    __slots__ = ()


class FSSpecUPath(UPath, PureFSSpecPath):
    __slots__ = ()
