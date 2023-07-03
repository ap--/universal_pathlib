from __future__ import annotations

import sys
from os import PathLike
from os import stat_result
from typing import AnyStr
from typing import Protocol

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias


__all__ = [
    "PathlibFlavour",
]


StrPath: TypeAlias = "str | PathLike[str]"
BytesPath: TypeAlias = "bytes | PathLike[bytes]"
StrOrBytesPath: TypeAlias = "str | bytes | PathLike[str] | PathLike[bytes]"


class PathlibFlavour(Protocol):
    sep: str
    altsep: str | None

    @staticmethod
    def splitroot(path: PathLike[AnyStr]) -> tuple[AnyStr, AnyStr, AnyStr]:
        ...

    @staticmethod
    def join(__a: PathLike[AnyStr], *paths: PathLike[AnyStr]) -> AnyStr:
        ...

    @staticmethod
    def splitdrive(p: PathLike[AnyStr]) -> tuple[AnyStr, AnyStr]:
        ...

    @staticmethod
    def normcase(s: PathLike[AnyStr]) -> AnyStr:
        ...

    @staticmethod
    def isabs(s: StrOrBytesPath) -> bool:
        ...

    @staticmethod
    def ismount(path: StrOrBytesPath) -> bool:
        ...

    @staticmethod
    def isjunction(path: StrOrBytesPath) -> bool:
        ...

    @staticmethod
    def samestat(s1: stat_result, s2: stat_result) -> bool:
        ...

    @staticmethod
    def abspath(path: PathLike[AnyStr]) -> AnyStr:
        ...

    @staticmethod
    def realpath(filename: PathLike[AnyStr], *, strict: bool = False) -> AnyStr:
        ...

    @staticmethod
    def expanduser(path: AnyStr) -> AnyStr:
        ...
