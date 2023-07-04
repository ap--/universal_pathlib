import ntpath
import os
import posixpath
from os import PathLike
from os import stat_result
from typing import AnyStr

from fsspec import get_filesystem_class
from fsspec.core import split_protocol
from fsspec.utils import stringify_path

from upath._types import PathlibFlavour
from upath._types import StrOrBytesPath

__all__ = [
    "fsspecpath",
]


def _ensure_str(s: str | bytes) -> str:
    if isinstance(s, str):
        return s
    else:
        return s.decode()


@object.__new__
class fsspecpath(PathlibFlavour):
    __slots__ = ()

    sep = "/"
    altsep = None

    @staticmethod
    def splitroot(path: PathLike[AnyStr]) -> tuple[AnyStr, AnyStr, AnyStr]:
        protocol, pth = split_protocol(path)
        root_marker = get_filesystem_class(protocol).root_marker
        has_root = pth.startswith(root_marker)
        if has_root:
            pth = pth[len(root_marker) :]
        if protocol is None and not has_root:
            out = "", "", _ensure_str(pth)
        elif protocol is None and has_root:
            out = "", f"file://{root_marker}", _ensure_str(pth)
        else:
            out = "", f"{protocol}://{root_marker}", _ensure_str(pth)
        return out  # type: ignore

    @staticmethod
    def join(__a: PathLike[AnyStr], *paths: PathLike[AnyStr]) -> AnyStr:
        protocol, pth = split_protocol(__a)
        joined = os.path.join(pth, *paths)
        if protocol is None:
            return joined
        else:
            return f"{protocol}://{joined}"  # type: ignore

    @staticmethod
    def splitdrive(p: PathLike[AnyStr]) -> tuple[AnyStr, AnyStr]:
        protocol, pth = split_protocol(p)
        if protocol is None:
            return os.path.splitdrive(pth)
        else:
            return "", os.fspath(p)  # type: ignore

    @staticmethod
    def normcase(s: PathLike[AnyStr]) -> AnyStr:
        protocol, pth = split_protocol(s)
        if protocol is None:
            if os.name == "nt":
                return ntpath.normcase(pth)
            else:
                return posixpath.normcase(pth)
        else:
            return os.fspath(s)

    @staticmethod
    def isabs(s: StrOrBytesPath) -> bool:
        protocol, pth = split_protocol(s)
        if protocol is None or protocol == "file":
            if os.name == "nt":
                return ntpath.isabs(pth)
            else:
                return posixpath.isabs(pth)
        else:
            return True

    @staticmethod
    def ismount(path: StrOrBytesPath) -> bool:
        protocol, pth = split_protocol(path)
        if protocol is None or protocol == "file":
            if os.name == "nt":
                return ntpath.ismount(pth)
            else:
                return posixpath.ismount(pth)
        else:
            return False

    @staticmethod
    def isjunction(path: StrOrBytesPath) -> bool:
        return False

    @staticmethod
    def samestat(s1: stat_result, s2: stat_result) -> bool:
        return os.path.samestat(s1, s2)

    @staticmethod
    def abspath(path: PathLike[AnyStr]) -> AnyStr:
        protocol, pth = split_protocol(path)
        if protocol is None or protocol == "file":
            if os.name == "nt":
                return ntpath.abspath(pth)
            else:
                return posixpath.abspath(pth)
        else:
            return stringify_path(path)

    @staticmethod
    def realpath(filename: PathLike[AnyStr], *, strict: bool = False) -> AnyStr:
        protocol, pth = split_protocol(filename)
        if protocol is None or protocol == "file":
            if os.name == "nt":
                return ntpath.realpath(pth)
            else:
                return posixpath.realpath(pth)
        else:
            return stringify_path(filename)

    @staticmethod
    def expanduser(path: AnyStr) -> AnyStr:
        protocol, pth = split_protocol(path)
        if protocol is None or protocol == "file":
            if os.name == "nt":
                return ntpath.expanduser(pth)
            else:
                return posixpath.expanduser(pth)
        else:
            return stringify_path(path)


class FSSpecStats:
    def __init__(self, info: dict) -> None:
        self._info = info

    @property
    def st_mode(self):
        return self._info["type"]
