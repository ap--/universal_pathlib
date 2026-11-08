"""tests for the experimental UPath.aio async accessor

The tests drive coroutines with asyncio.run() directly, so they don't
require an async pytest plugin.
"""

from __future__ import annotations

import asyncio

import pytest
from fsspec.implementations.memory import MemoryFileSystem
from fsspec.registry import _registry as fsspec_registry_private
from fsspec.registry import register_implementation as fsspec_register_implementation

from upath import UnsupportedOperation
from upath import UPath
from upath._aio import UPathAsyncAccessor
from upath._aio import _native_async_fs
from upath.implementations.memory import MemoryPath
from upath.registry import _registry
from upath.registry import get_upath_class
from upath.registry import register_implementation

try:
    from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
except ImportError:  # fsspec < 2024.12.0
    AsyncFileSystemWrapper = None


async def _collect(ait):
    return [x async for x in ait]


@pytest.fixture
def memory_path(clear_fsspec_memory_cache):
    path = UPath("memory:///aio")
    path.joinpath("folder").mkdir(parents=True)
    path.joinpath("folder", "a.txt").write_bytes(b"aaa")
    path.joinpath("folder", "b.txt").write_bytes(b"bbb")
    return path


def test_aio_returns_accessor():
    p = UPath("memory:///a.txt")
    assert isinstance(p.aio, UPathAsyncAccessor)
    assert p.aio.upath is p


def test_aio_requires_running_loop(memory_path):
    with pytest.raises(RuntimeError):
        _native_async_fs(memory_path)


def test_sync_filesystem_fallback(memory_path):
    file = memory_path / "folder" / "a.txt"
    folder = memory_path / "folder"
    missing = memory_path / "missing.txt"

    async def main():
        assert _native_async_fs(file) is None
        return (
            await file.aio.exists(),
            await missing.aio.exists(),
            await file.aio.is_file(),
            await folder.aio.is_dir(),
            (await file.aio.stat()).st_size,
            await file.aio.read_bytes(),
            sorted(await _collect(folder.aio.iterdir())),
        )

    assert asyncio.run(main()) == (
        True,
        False,
        True,
        True,
        3,
        b"aaa",
        [folder / "a.txt", folder / "b.txt"],
    )


def test_sync_filesystem_fallback_write(memory_path):
    file = memory_path / "folder" / "c.txt"

    async def main():
        n_bytes = await file.aio.write_bytes(b"ccc")
        n_chars = await file.with_name("d.txt").aio.write_text("dd\n", newline="\n")
        return n_bytes, n_chars, await file.with_name("d.txt").aio.read_text()

    assert asyncio.run(main()) == (3, 3, "dd\n")
    assert file.read_bytes() == b"ccc"


def test_sync_filesystem_fallback_errors(memory_path):
    async def read_missing():
        await (memory_path / "missing.txt").aio.read_bytes()

    async def iterdir_file():
        await _collect((memory_path / "folder" / "a.txt").aio.iterdir())

    with pytest.raises(FileNotFoundError):
        asyncio.run(read_missing())
    with pytest.raises(NotADirectoryError):
        asyncio.run(iterdir_file())


def test_local_path_fallback(tmp_path):
    base = UPath(tmp_path)
    file = base / "file.txt"

    async def main():
        await file.aio.write_text("local")
        children = await _collect(base.aio.iterdir())
        return await file.aio.read_text(), children

    text, children = asyncio.run(main())
    assert text == "local"
    assert children == [file]
    assert type(children[0]) is type(base)


# --- native async filesystems ------------------------------------------------


class AsyncMemoryFileSystem(AsyncFileSystemWrapper or object):  # type: ignore[misc]
    """the memory filesystem exposed through the fsspec async API"""

    protocol = "asyncmemory"
    root_marker = "/"
    calls: list[tuple[str, bool]] = []

    def __init__(self, *args, asynchronous=False, loop=None, **kwargs):
        super().__init__(MemoryFileSystem(), asynchronous=asynchronous, loop=loop)
        self.protocol = "asyncmemory"
        for name in ["_cat_file", "_pipe_file", "_info", "_ls", "_exists", "_isdir"]:
            setattr(self, name, self._record(name, getattr(self, name)))

    def _record(self, name, coro_func):
        async def wrapper(*args, **kwargs):
            self.calls.append((name, self.asynchronous))
            return await coro_func(*args, **kwargs)

        return wrapper

    @classmethod
    def _strip_protocol(cls, path):
        path = str(path)
        if path.startswith("asyncmemory://"):
            path = path[len("asyncmemory://") :]
        return MemoryFileSystem._strip_protocol(path)


class AsyncMemoryPath(MemoryPath):
    __slots__ = ()


@pytest.fixture
def async_memory_path(memory_path):
    if AsyncFileSystemWrapper is None:
        pytest.skip("requires fsspec.implementations.asyn_wrapper")
    saved_upath_registry = _registry._m.maps[0].copy()
    fsspec_register_implementation("asyncmemory", AsyncMemoryFileSystem, clobber=True)
    register_implementation("asyncmemory", AsyncMemoryPath, clobber=True)
    AsyncMemoryFileSystem.calls.clear()
    try:
        yield UPath("asyncmemory:///aio")
    finally:
        fsspec_registry_private.pop("asyncmemory", None)
        _registry._m.maps[0].clear()
        _registry._m.maps[0].update(saved_upath_registry)
        get_upath_class.cache_clear()


def test_native_async_filesystem(async_memory_path):
    folder = async_memory_path / "folder"
    file = folder / "a.txt"
    assert isinstance(file, AsyncMemoryPath)

    async def main():
        afs = _native_async_fs(file)
        assert isinstance(afs, AsyncMemoryFileSystem)
        assert afs.asynchronous
        assert afs is not file.fs
        return (
            await file.aio.exists(),
            await file.aio.is_file(),
            await folder.aio.is_dir(),
            (await file.aio.stat()).st_size,
            await file.aio.read_bytes(),
            sorted(await _collect(folder.aio.iterdir())),
        )

    assert asyncio.run(main()) == (
        True,
        True,
        True,
        3,
        b"aaa",
        [folder / "a.txt", folder / "b.txt"],
    )
    called = {name for name, asynchronous in AsyncMemoryFileSystem.calls}
    assert {"_exists", "_info", "_cat_file", "_isdir", "_ls"} <= called
    assert all(asynchronous for _, asynchronous in AsyncMemoryFileSystem.calls)


def test_native_async_filesystem_write(async_memory_path):
    file = async_memory_path / "folder" / "c.txt"

    async def main():
        n_bytes = await file.aio.write_bytes(bytearray(b"ccc"))
        n_chars = await file.with_name("d.txt").aio.write_text("d\n", newline="\r\n")
        return n_bytes, n_chars, await file.with_name("d.txt").aio.read_text()

    assert asyncio.run(main()) == (3, 2, "d\n")
    assert ("_pipe_file", True) in AsyncMemoryFileSystem.calls
    # same store as the synchronous memory filesystem
    assert UPath("memory:///aio/folder/c.txt").read_bytes() == b"ccc"
    assert UPath("memory:///aio/folder/d.txt").read_bytes() == b"d\r\n"


def test_native_async_filesystem_errors(async_memory_path):
    async def read_missing():
        await (async_memory_path / "missing.txt").aio.read_bytes()

    async def iterdir_file():
        await _collect((async_memory_path / "folder" / "a.txt").aio.iterdir())

    with pytest.raises(FileNotFoundError):
        asyncio.run(read_missing())
    with pytest.raises(NotADirectoryError):
        asyncio.run(iterdir_file())


def test_native_async_filesystem_cached_per_loop(async_memory_path):
    async def get_fs():
        fs0 = _native_async_fs(async_memory_path)
        fs1 = _native_async_fs(async_memory_path / "folder" / "a.txt")
        assert fs0 is fs1
        return fs0

    fs_loop0 = asyncio.run(get_fs())
    fs_loop1 = asyncio.run(get_fs())
    assert fs_loop0 is not fs_loop1


def test_native_async_respects_sync_overrides(async_memory_path):
    class ReadOnlyAsyncMemoryPath(AsyncMemoryPath):
        __slots__ = ()

        def write_bytes(self, data):
            raise UnsupportedOperation("read-only")

    register_implementation("asyncmemory", ReadOnlyAsyncMemoryPath, clobber=True)
    path = UPath("asyncmemory:///aio/folder/a.txt")
    assert isinstance(path, ReadOnlyAsyncMemoryPath)

    async def main():
        assert _native_async_fs(path, "write_bytes") is None
        assert _native_async_fs(path, "read_bytes") is not None
        await path.aio.write_bytes(b"x")

    with pytest.raises(UnsupportedOperation, match="read-only"):
        asyncio.run(main())
    assert path.read_bytes() == b"aaa"


def test_concurrent_reads(memory_path):
    files = [memory_path / "folder" / f"{i}.txt" for i in range(20)]
    for i, f in enumerate(files):
        f.write_text(str(i))

    async def main():
        return await asyncio.gather(*(f.aio.read_text() for f in files))

    assert asyncio.run(main()) == [str(i) for i in range(20)]
