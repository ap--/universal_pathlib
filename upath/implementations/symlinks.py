"""upath.implementations.symlinks: emulated symlinks on any filesystem

Experimental prototype, see `upath._symlinkfs.SymlinkFileSystem`.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Any

from fsspec.registry import register_implementation as _fsspec_register_implementation

from upath._stat import UPathStatResult
from upath._symlinkfs import SymlinkFileSystem
from upath._symlinkfs import _is_relative_target
from upath.core import UPath
from upath.types import PathInfo
from upath.types import ReadablePathLike
from upath.types import StatResultType

if TYPE_CHECKING:
    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self

    from fsspec import AbstractFileSystem

__all__ = ["SymlinkPath"]

_fsspec_register_implementation(SymlinkFileSystem.protocol, SymlinkFileSystem)


class _SymlinkPathInfo(PathInfo):
    __slots__ = ("_fs", "_path")

    def __init__(self, path: SymlinkPath) -> None:
        self._fs = path.fs
        self._path = path.path

    def _type(self, follow_symlinks: bool) -> str | None:
        try:
            return self._fs.info(self._path, follow_symlinks=follow_symlinks)["type"]
        except OSError:
            return None

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        return self._type(follow_symlinks) is not None

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._type(follow_symlinks) == "directory"

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self._type(follow_symlinks) == "file"

    def is_symlink(self) -> bool:
        return self._fs.islink(self._path)


class SymlinkPath(UPath):
    """UPath for the `symlinks::<target-url>` chained filesystem (experimental)"""

    __slots__ = ()

    if TYPE_CHECKING:
        fs: SymlinkFileSystem  # type: ignore[assignment]

    @classmethod
    def _fs_factory(
        cls,
        urlpath: str,
        protocol: str,
        storage_options: Mapping[str, Any],
    ) -> AbstractFileSystem:
        so = dict(storage_options)
        so.pop("fo", None)
        return super()._fs_factory(urlpath, protocol, so)

    @property
    def storage_options(self) -> Mapping[str, Any]:
        so = self._storage_options.copy()
        so.pop("fo", None)
        return MappingProxyType(so)

    @property
    def info(self) -> PathInfo:
        return _SymlinkPathInfo(self)

    def is_symlink(self) -> bool:
        return self.fs.islink(self.path)

    def readlink(self) -> Self:
        target = self.fs.readlink(self.path)
        if _is_relative_target(target):
            parent = self.parent
            return parent.joinpath(target).relative_to(parent)
        return self.with_segments(self.fs._join(self.fs._split(target)))

    def symlink_to(
        self,
        target: ReadablePathLike,
        target_is_directory: bool = False,
    ) -> None:
        if isinstance(target, UPath):
            target = target.path
        self.fs.symlink(str(target), self.path)

    def stat(self, *, follow_symlinks: bool = True) -> StatResultType:
        return UPathStatResult.from_info(
            self.fs.info(self.path, follow_symlinks=follow_symlinks)
        )

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        if not follow_symlinks:
            return self.fs.lexists(self.path)
        return self.fs.exists(self.path)

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self.info.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self.info.is_file(follow_symlinks=follow_symlinks)

    def resolve(self, strict: bool = False) -> Self:
        if self._relative_base is not None:
            self = self.absolute()
        resolved = self.with_segments(self.fs._resolve(self.path))
        if strict and not resolved.exists():
            raise FileNotFoundError(str(self))
        return resolved
