"""upath.backport of stdlib pathlib

This submodule provides a backport of Python's stdlib pathlib to
simplify python version support in universal_pathlib.
"""

from upath._pathlib_backport._pathlib import Path as Path
from upath._pathlib_backport._pathlib import PosixPath as PosixPath
from upath._pathlib_backport._pathlib import PurePath as PurePath
from upath._pathlib_backport._pathlib import WindowsPath as WindowsPath

PATHLIB_PYTHON_VERSION_INFO = (3, 12)
PATHLIB_PYTHON_COMMIT_HASH = "ae25f1c8e5522dee4131a3b48490cdb199e9ae22"

__all__ = [
    "PurePath",
    "Path",
    "PosixPath",
    "WindowsPath",
]
