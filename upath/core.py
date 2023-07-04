from __future__ import annotations

import os
import sys

from fsspec import get_filesystem_class
from fsspec.core import split_protocol
from fsspec.core import strip_protocol
from fsspec.spec import AbstractFileSystem

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
    __slots__ = ("_protocol", "_storage_options", "_cached_fs")

    def __new__(cls, *args, **kwargs):
        if cls is UPath:
            if (
                (args and split_protocol(args[0])[0] is not None)
                or kwargs.get("protocol")
                or kwargs.get("fs")
            ):
                cls = FSSpecUPath
            else:
                cls = WindowsUPath if os.name == "nt" else PosixUPath
        return object.__new__(cls)

    @property
    def fs(self) -> AbstractFileSystem:
        try:
            return self._cached_fs
        except AttributeError:
            fs_cls = get_filesystem_class(self._protocol)
            self._cached_fs = fs = fs_cls(**self._storage_options)
            return fs

    @property
    def path(self) -> str:
        return strip_protocol(self)


class PosixUPath(UPath, PosixPath):
    __slots__ = ()


class WindowsUPath(UPath, WindowsPath):
    __slots__ = ()


class FSSpecUPath(UPath, PureFSSpecPath):
    __slots__ = ()
