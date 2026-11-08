import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fsspec.implementations.memory import MemoryFileSystem

from upath import UPath
from upath._chain import FSSpecChainParser


@pytest.mark.parametrize(
    "urlpath,expected",
    [
        ("simplecache::file://tmp", "simplecache"),
        ("zip://file.txt::file://tmp.zip", "zip"),
    ],
)
def test_chaining_upath_protocol(urlpath, expected):
    pth = UPath(urlpath)
    assert pth.protocol == expected


def add_current_drive_on_windows(pth: str) -> str:
    drive = os.path.splitdrive(Path.cwd().as_posix())[0]
    return f"{drive}{pth}"


@pytest.mark.parametrize(
    "urlpath,expected",
    [
        pytest.param(
            "simplecache::file:///tmp",
            add_current_drive_on_windows("/tmp"),
        ),
        pytest.param(
            "zip://file.txt::file:///tmp.zip",
            "file.txt",
        ),
        pytest.param(
            "zip://a/b/c.txt::simplecache::memory://zipfile.zip",
            "a/b/c.txt",
        ),
    ],
)
def test_chaining_upath_path(urlpath, expected):
    pth = UPath(urlpath)
    assert pth.path == expected


@pytest.mark.parametrize(
    "urlpath,expected",
    [
        (
            "simplecache::file:///tmp",
            {
                "target_protocol": "file",
                "target_options": {},
            },
        ),
    ],
)
def test_chaining_upath_storage_options(urlpath, expected):
    pth = UPath(urlpath)
    assert dict(pth.storage_options) == expected


@pytest.mark.parametrize(
    "urlpath,expected",
    [
        ("simplecache::memory://tmp", ("/", "tmp")),
    ],
)
def test_chaining_upath_parts(urlpath, expected):
    pth = UPath(urlpath)
    assert pth.parts == expected


@pytest.mark.parametrize(
    "urlpath,expected",
    [
        ("simplecache::memory:///tmp", "simplecache::memory:///tmp"),
    ],
)
def test_chaining_upath_str(urlpath, expected):
    pth = UPath(urlpath)
    assert str(pth) == expected


@pytest.fixture
def clear_memory_fs():
    fs = MemoryFileSystem()
    store = fs.store
    pseudo_dirs = fs.pseudo_dirs
    try:
        yield fs
    finally:
        fs.store.clear()
        fs.store.update(store)
        fs.pseudo_dirs[:] = pseudo_dirs


@pytest.fixture
def memory_file_urlpath(clear_memory_fs):
    fs = clear_memory_fs
    fs.pipe_file("/abc/file.txt", b"hello world")
    yield fs.unstrip_protocol("/abc/file.txt")


def test_read_file(memory_file_urlpath):
    pth = UPath(f"simplecache::{memory_file_urlpath}")
    assert pth.read_bytes() == b"hello world"


def test_write_file(clear_memory_fs):
    pth = UPath("simplecache::memory://abc.txt")
    pth.write_bytes(b"hello world")
    assert clear_memory_fs.cat_file("abc.txt") == b"hello world"


@pytest.mark.parametrize(
    "urlpath",
    [
        "memory:///file.txt",
        "simplecache::memory:///tmp",
        "zip://file.txt::memory:///tmp.zip",
        "zip://a/b/c.txt::simplecache::memory:///zipfile.zip",
        "simplecache::zip://a/b/c.txt::tar://blah.zip::memory:///file.tar",
    ],
)
def test_chain_parser_roundtrip(urlpath: str):
    parser = FSSpecChainParser()
    segments = parser.unchain(urlpath, protocol=None, storage_options={})
    rechained, kw = parser.chain(segments)
    assert rechained == urlpath
    assert kw == {}


@pytest.fixture
def memory_zip_urlpath(clear_memory_fs):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("abc/efg.csv", "a,b\n1,2\n")
    clear_memory_fs.pipe_file("/bucket/file.zip", buf.getvalue())
    yield "memory:///bucket/file.zip"


@pytest.mark.parametrize(
    "urlpath",
    [
        "memory:///bucket/file.txt",
        "file:///tmp/file.txt",
        "/tmp/file.txt",
    ],
)
def test_chain_single_segment(urlpath):
    pth = UPath(urlpath)
    assert len(pth.chain) == 1
    assert pth.chain[0] is pth


def test_chain_relative_path():
    pth = UPath("memory:///a/b").relative_to(UPath("memory:///a"))
    assert pth.chain == (pth,)


def test_chain_zip_on_memory(memory_zip_urlpath):
    pth = UPath(f"zip://abc/efg.csv::{memory_zip_urlpath}")
    assert len(pth.chain) == 2
    assert pth.chain[0] is pth
    assert [type(p).__name__ for p in pth.chain] == ["ZipPath", "MemoryPath"]

    archive = pth.chain[-1]
    assert archive == UPath(memory_zip_urlpath)
    assert archive.path == "/bucket/file.zip"
    assert archive.is_file()
    assert archive.read_bytes().startswith(b"PK")
    assert archive.chain == (archive,)


def test_chain_zip_on_local(tmp_path):
    archive = tmp_path.joinpath("file.zip")
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("abc/efg.csv", "a,b\n1,2\n")
    pth = UPath(f"zip://abc/efg.csv::{archive.as_uri()}")
    assert pth.read_text() == "a,b\n1,2\n"

    inner = pth.chain[-1]
    assert inner.protocol == "file"
    assert inner == UPath(archive.as_uri())
    assert inner.read_bytes() == archive.read_bytes()


def test_chain_simplecache(clear_memory_fs):
    clear_memory_fs.pipe_file("/bucket/key", b"hello")
    pth = UPath("simplecache::memory://bucket/key")
    assert pth.read_bytes() == b"hello"

    target = pth.chain[1]
    assert type(target).__name__ == "MemoryPath"
    assert target == UPath("memory:///bucket/key")
    target.write_bytes(b"updated")
    assert target.read_bytes() == b"updated"


@pytest.mark.parametrize(
    "urlpath,protocols,strs",
    [
        (
            "simplecache::zip://abc/efg.csv::memory://bucket/file.zip",
            ["simplecache", "zip", "memory"],
            [
                "simplecache::zip://abc/efg.csv::memory:///bucket/file.zip",
                "zip://abc/efg.csv::memory:///bucket/file.zip",
                "memory://bucket/file.zip",
            ],
        ),
        (
            "zip://abc/efg.csv::simplecache::memory://bucket/file.zip",
            ["zip", "simplecache", "memory"],
            [
                "zip://abc/efg.csv::simplecache::memory:///bucket/file.zip",
                "simplecache::memory:///bucket/file.zip",
                "memory://bucket/file.zip",
            ],
        ),
    ],
)
def test_chain_three_segments(memory_zip_urlpath, urlpath, protocols, strs):
    pth = UPath(urlpath)
    assert [p.protocol for p in pth.chain] == protocols
    assert [str(p) for p in pth.chain] == strs
    assert pth.chain[1].chain == pth.chain[1:]
    assert all(p.exists() for p in pth.chain)


def test_chain_segment_storage_options(memory_zip_urlpath):
    pth = UPath(
        f"zip://abc/efg.csv::{memory_zip_urlpath}",
        memory={"skip_instance_cache": True},
    )
    assert dict(pth.chain[-1].storage_options) == {"skip_instance_cache": True}
    assert pth.chain[-1].read_bytes().startswith(b"PK")


def test_chain_segment_path_operations(memory_zip_urlpath):
    pth = UPath(f"zip://abc/efg.csv::{memory_zip_urlpath}")
    archive = pth.chain[-1]
    assert str(archive.with_name("other.zip")) == "memory://bucket/other.zip"
    assert str(pth.parent) == "zip://abc::memory:///bucket/file.zip"
    assert pth.parent.chain[-1] == archive
