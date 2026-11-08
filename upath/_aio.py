"""upath._aio module: experimental asynchronous API for UPath instances

Access it via the `UPath.aio` property:

>>> from upath import UPath
>>> async def main():
...     p = UPath("memory:///folder/file.txt")
...     await p.aio.write_text("hello")
...     return await p.aio.read_text()

Filesystems that implement the fsspec async API (`async_impl = True`) are
used natively: an `asynchronous=True` filesystem instance is created inside
the running event loop and cached per loop. All other paths (synchronous
filesystems, `PosixUPath` / `WindowsUPath` and UPath subclasses that
override the corresponding sync method) run the regular sync method in a
worker thread via `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import io
import weakref
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from typing import Generic
from typing import TypeVar
from typing import cast

from fsspec.registry import get_filesystem_class
from fsspec.utils import tokenize

from upath._stat import UPathStatResult

if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem

    from upath.core import UPath
    from upath.types import StatResultType

__all__ = ["UPathAsyncAccessor"]

_PT = TypeVar("_PT")

# asynchronous filesystem instances are bound to the loop they were created in
_ASYNC_FS_CACHE: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[str, AsyncFileSystem]
] = weakref.WeakKeyDictionary()


def _native_async_fs(path: UPath, *methods: str) -> AsyncFileSystem | None:
    """return a loop-bound asynchronous filesystem for path or None

    None is returned if the filesystem is synchronous, or if the UPath
    subclass overrides one of the given sync methods (in which case the
    async variant must run the override to keep the semantics identical).
    """
    from upath.core import UPath

    loop = asyncio.get_running_loop()

    protocol = path.protocol
    if not protocol:
        return None  # PosixUPath / WindowsUPath are pathlib based
    cls = type(path)
    if any(getattr(cls, m) is not getattr(UPath, m) for m in methods):
        return None
    try:
        fs_cls = get_filesystem_class(protocol)
    except (ImportError, ValueError):
        return None
    if not getattr(fs_cls, "async_impl", False):
        return None

    storage_options = {
        k: v
        for k, v in path.storage_options.items()
        if k not in {"asynchronous", "loop"}
    }
    token = tokenize(cls, protocol, storage_options)
    fs_cache = _ASYNC_FS_CACHE.setdefault(loop, {})
    try:
        return fs_cache[token]
    except KeyError:
        fs = fs_cache[token] = cls._fs_factory(
            str(path),
            protocol,
            {**storage_options, "asynchronous": True, "skip_instance_cache": True},
        )
        return fs


class UPathAsyncAccessor(Generic[_PT]):
    """Asynchronous versions of a UPath's I/O methods (experimental)"""

    __slots__ = ("_path",)

    if TYPE_CHECKING:
        _path: UPath

    def __init__(self, path: _PT) -> None:
        self._path = path  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._path!r})"

    @property
    def upath(self) -> _PT:
        """The (synchronous) path this accessor operates on."""
        return cast(_PT, self._path)

    async def exists(self) -> bool:
        afs = _native_async_fs(self._path, "exists")
        if afs is None:
            return await asyncio.to_thread(self._path.exists)
        return await afs._exists(self._path.path)

    async def is_dir(self) -> bool:
        afs = _native_async_fs(self._path, "is_dir")
        if afs is None:
            return await asyncio.to_thread(self._path.is_dir)
        return await afs._isdir(self._path.path)

    async def is_file(self) -> bool:
        afs = _native_async_fs(self._path, "is_file")
        if afs is None:
            return await asyncio.to_thread(self._path.is_file)
        return await afs._isfile(self._path.path)

    async def stat(self) -> StatResultType:
        afs = _native_async_fs(self._path, "stat")
        if afs is None:
            return await asyncio.to_thread(self._path.stat)
        return UPathStatResult.from_info(await afs._info(self._path.path))

    async def read_bytes(self) -> bytes:
        afs = _native_async_fs(self._path, "read_bytes", "open", "__open_reader__")
        if afs is None:
            return await asyncio.to_thread(self._path.read_bytes)
        return await afs._cat_file(self._path.path)

    async def read_text(
        self,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        afs = _native_async_fs(self._path, "read_text", "open", "__open_reader__")
        if afs is None:
            return await asyncio.to_thread(
                self._path.read_text,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
        data = await afs._cat_file(self._path.path)
        buffer = io.TextIOWrapper(
            io.BytesIO(data), encoding=encoding, errors=errors, newline=newline
        )
        return buffer.read()

    async def write_bytes(self, data: bytes) -> int:
        afs = _native_async_fs(self._path, "write_bytes", "open", "__open_writer__")
        if afs is None:
            return await asyncio.to_thread(self._path.write_bytes, data)
        view = memoryview(data)
        await afs._pipe_file(self._path.path, view.tobytes())
        return view.nbytes

    async def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        afs = _native_async_fs(self._path, "write_text", "open", "__open_writer__")
        if afs is None:
            return await asyncio.to_thread(
                self._path.write_text,
                data,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
        if not isinstance(data, str):
            raise TypeError(f"data must be str, not {type(data).__name__}")
        raw = io.BytesIO()
        buffer = io.TextIOWrapper(
            raw, encoding=encoding, errors=errors, newline=newline
        )
        num_chars = buffer.write(data)
        buffer.flush()
        await afs._pipe_file(self._path.path, raw.getvalue())
        return num_chars

    async def iterdir(self) -> AsyncIterator[_PT]:
        afs = _native_async_fs(self._path, "iterdir")
        if afs is None:
            children = await asyncio.to_thread(lambda: list(self._path.iterdir()))
            for child in children:
                yield cast(_PT, child)
            return

        # mirrors UPath.iterdir
        sep = self._path.parser.sep
        base = self._path
        if base.parts[-1:] == ("",):
            base = base.parent
        base_path = base.path
        if not await afs._isdir(base_path):
            raise NotADirectoryError(str(self._path))
        for name in await afs._ls(base_path, detail=False):
            if isinstance(name, dict):
                name = name.get("name")
            if name in {".", ".."}:
                continue
            _, _, name = name.removesuffix(sep).rpartition(sep)
            yield cast(_PT, base.with_segments(base_path, name))
