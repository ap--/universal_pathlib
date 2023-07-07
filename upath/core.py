from __future__ import annotations

import os
import sys
import warnings

from fsspec import get_filesystem_class
from fsspec.core import split_protocol
from fsspec.core import strip_protocol
from fsspec.spec import AbstractFileSystem
from fsspec.utils import get_protocol
from fsspec.utils import stringify_path

from upath._flavour import FSSpecStats
from upath._flavour import fsspecpath
from upath.registry import get_upath_class

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

    def relative_to(self, other, /, *, walk_up=False):
        if not isinstance(other, UPath):
            other = UPath(other)
        if (
            other.__class__ is not self.__class__
            or other.fs.storage_options != self.fs.storage_options
        ):
            raise ValueError(f"{self!r} and {other!r} are not of compatible classes.")
        other = self.with_segments(other)
        for step, path in enumerate([other] + list(other.parents)):  # noqa
            if self.is_relative_to(path):
                break
        else:
            raise ValueError(f"{str(self)!r} and {str(other)!r} have different anchors")
        if step and not walk_up:
            raise ValueError(f"{str(self)!r} is not in the subpath of {str(other)!r}")
        parts = [".."] * step + self._tail[len(path._tail) :]
        return path.joinpath(*parts)

    def is_relative_to(self, other):
        """Return True if the path is relative to another path or False."""
        if not isinstance(other, UPath):
            other = UPath(other)
        if (
            other.__class__ is not self.__class__
            or other.fs.storage_options != self.fs.storage_options
        ):
            raise ValueError(f"{self!r} and {other!r} are not of compatible classes.")
        return self == other or other in self.parents

    def with_segments(self, *pathsegments):
        kw = {}
        try:
            kw["protocol"] = self._protocol
        except AttributeError:
            pass
        try:
            kw["storage_options"] = self._storage_options
        except AttributeError:
            pass
        return type(self)(*pathsegments, **kw)


class UPath(Path):
    __slots__ = ("_protocol", "_storage_options", "_cached_fs")

    def __new__(cls, *args, **kwargs):
        is_upath = cls is UPath
        uses_fsspec = lambda: (  # noqa
            (args and split_protocol(args[0])[0] is not None)
            or kwargs.get("protocol")
            or kwargs.get("fs")
        )

        if is_upath and uses_fsspec():
            return FSSpecUPath(*args, **kwargs)

        elif is_upath and os.name != "nt":
            return object.__new__(PosixUPath)

        elif is_upath and os.name == "nt":
            return object.__new__(WindowsUPath)

        else:
            return object.__new__(cls)

    def __reduce__(self):
        kw = {}
        for slot in ["_protocol", "_storage_options"]:
            try:
                kw[slot] = getattr(self, slot)
            except AttributeError:
                pass
        return type(self), (str(self),), (None, kw)

    @property
    def fs(self) -> AbstractFileSystem:
        try:
            return self._cached_fs
        except AttributeError:
            raise NotImplementedError("implement in subclass")

    @property
    def path(self) -> str:
        return strip_protocol(str(self))

    @property
    def _url(self):
        from urllib.parse import urlsplit

        warnings.warn(
            "UPath._url is going to be removed in the next major version!",
            category=DeprecationWarning,
            stacklevel=2,
        )
        return urlsplit(str(self))


class PosixUPath(UPath, PosixPath):
    __slots__ = ()

    if os.name == "nt":
        __new__ = PosixPath.__new__

    @property
    def fs(self):
        try:
            return self._cached_fs
        except AttributeError:
            from fsspec.implementations.local import LocalFileSystem

            self._cached_fs = fs = LocalFileSystem()
            return fs


class WindowsUPath(UPath, WindowsPath):
    __slots__ = ()

    if os.name != "nt":
        __new__ = WindowsPath.__new__

    @property
    def fs(self):
        try:
            return self._cached_fs
        except AttributeError:
            from fsspec.implementations.local import LocalFileSystem

            self._cached_fs = fs = LocalFileSystem()
            return fs


class FSSpecUPath(UPath, PureFSSpecPath):
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        fs = kwargs.get("fs")
        if fs:
            protocol = fs.protocol if isinstance(fs.protocol, str) else fs.protocol[0]
        else:
            protocol = kwargs.get(
                "protocol", split_protocol(args[0])[0] if args else None
            )
        if protocol is None:
            raise ValueError("must provide protocol when instantiating FSSpecUPath")

        upath_cls = get_upath_class(protocol)
        return object.__new__(upath_cls)

    def __init__(self, *args, **kwargs):
        if args:
            arg0 = args[0]
            if isinstance(arg0, FSSpecUPath):
                _p = arg0.fs.protocol
                protocol = _p if isinstance(_p, str) else _p[0]
                storage_options = arg0.fs.storage_options.copy()
            else:
                protocol = get_protocol(stringify_path(args[0]))
                storage_options = {}
        else:
            protocol = "file"
            storage_options = {}

        self._protocol = kwargs.pop("protocol", protocol)
        self._storage_options = kwargs.pop("storage_options", storage_options)
        if kwargs:
            warnings.warn(
                "please provide filesystem storage options as a dict via the "
                "`storage_options` keyword argument",
                category=PendingDeprecationWarning,
                stacklevel=2,
            )
            self._storage_options.update(kwargs)
            kwargs.clear()
        super().__init__(*args, **kwargs)

    @property
    def fs(self) -> AbstractFileSystem:
        try:
            return self._cached_fs
        except AttributeError:
            fs_cls = get_filesystem_class(self._protocol)
            self._cached_fs = fs = fs_cls(**self._storage_options)
            return fs

    def as_uri(self):
        return str(self)

    def stat(self, *, follow_symlinks=True):
        return FSSpecStats(self.fs.info(self.path))

    def lstat(self):
        return self.stat()

    def exists(self, *, follow_symlinks=True):
        return self.fs.exists(self.path)

    def is_dir(self):
        return self.fs.isdir(self.path)

    def is_file(self):
        return self.fs.isfile(self.path)

    def is_mount(self):
        return False

    def is_symlink(self):
        return False

    def is_junction(self):
        return False

    def is_block_device(self):
        return False

    def is_char_device(self):
        return False

    def is_fifo(self):
        return False

    def is_socket(self):
        return False

    def samefile(self, other_path):
        st = self.stat()
        try:
            other_st = other_path.stat()
        except AttributeError:
            other_st = self.with_segments(other_path).stat()
        return self._flavour.samestat(st, other_st)

    def open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        return self.fs.open(self.path, mode=mode)

    def read_bytes(self):
        with self.open(mode="rb") as f:
            return f.read()

    def read_text(self, encoding=None, errors=None):
        with self.open(mode="rt", encoding=encoding, errors=errors) as f:
            return f.read()

    def write_bytes(self, data):
        # type-check for the buffer interface before truncating the file
        view = memoryview(data)
        with self.open(mode="wb") as f:
            return f.write(view)

    def write_text(self, data, encoding=None, errors=None, newline=None):
        if not isinstance(data, str):
            raise TypeError("data must be str, not %s" % data.__class__.__name__)
        with self.open(
            mode="w", encoding=encoding, errors=errors, newline=newline
        ) as f:
            return f.write(data)

    def iterdir(self):
        if self.is_file():
            raise NotADirectoryError(f"{self}")
        for pth in self.fs.ls(self.path, detail=False):
            yield self.__class__(
                pth,
                protocol=self._protocol,
                storage_options=self._storage_options,
            )

    def _make_child_relpath(self, name):
        raise NotImplementedError("removed")

    def glob(self, pattern, *, case_sensitive=None):
        if "**" in pattern:
            sep = self._flavour.sep
            pparts = pattern.split(sep)
            patterns = (
                sep.join([p for p in pparts if p != "**"]),
                pattern,
            )
        else:
            patterns = (pattern,)
        return [
            self.__class__(
                p,
                protocol=self._protocol,
                storage_options=self._storage_options,
            )
            for pattern in patterns
            for p in self.fs.glob(self.joinpath(pattern).path)
        ]

    def rglob(self, pattern, *, case_sensitive=None):
        return [
            self.__class__(
                p,
                protocol=self._protocol,
                storage_options=self._storage_options,
            )
            for r in [
                self.fs.glob(self.joinpath(pattern).path),
                self.fs.glob(self.joinpath("**", pattern).path),
            ]
            for p in r
        ]

    def walk(self, top_down=True, on_error=None, follow_symlinks=False):
        for _ in self.fs.walk(self.path):  # todo
            raise NotImplementedError("todo")

    @classmethod
    def cwd(cls):
        raise NotImplementedError("unsupported")

    @classmethod
    def home(cls):
        raise NotImplementedError("unsupported")

    def absolute(self):
        return self

    def resolve(self, strict=False):
        return self

    def owner(self):
        raise NotImplementedError("Path.owner() is unsupported on this system")

    def group(self):
        raise NotImplementedError("Path.group() is unsupported on this system")

    def readlink(self):
        raise NotImplementedError("os.readlink() not available on this system")

    def touch(self, mode=0o666, exist_ok=True):
        self.fs.touch(self.path)

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        try:
            self.fs.mkdir(self.path)
        except FileExistsError:
            if not exist_ok:
                raise

    def chmod(self, mode, *, follow_symlinks=True):
        raise NotImplementedError

    def lchmod(self, mode):
        raise NotImplementedError

    def unlink(self, missing_ok=False):
        try:
            self.fs.delete(self.path)
        except FileNotFoundError:
            if missing_ok:
                pass
            else:
                raise

    def rmdir(self):
        if self.is_file():
            raise NotADirectoryError(f"{self}")
        try:
            next(self.iterdir())
        except StopIteration:
            self.fs.rm(self.path)
        else:
            raise OSError("not empty")

    def rename(self, target):
        target = UPath(target)
        if not target.is_absolute():
            target = self.parent.joinpath(target)
        self.fs.rename(self.path, target.path)
        return target

    def replace(self, target):  # todo
        os.replace(self, target)
        return self.with_segments(target)

    def symlink_to(self, target, target_is_directory=False):
        raise NotImplementedError("os.symlink() not available on this system")

    def hardlink_to(self, target):
        raise NotImplementedError("os.link() not available on this system")

    def expanduser(self):
        raise NotImplementedError
