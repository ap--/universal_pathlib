"""tests for the experimental symlinks:: chained filesystem"""

from __future__ import annotations

import errno
import stat

import fsspec
import pytest

from upath import UPath
from upath._symlinkfs import SymlinkFileSystem
from upath.implementations.symlinks import SymlinkPath

MAPPING = {
    "/data/latest": "v2",
    "/data/current.txt": "/data/v1/a.txt",
    "/data/up": "../data/v1",
    "/data/dangling": "missing",
    "/data/loop1": "loop2",
    "/data/loop2": "/data/loop1",
}


@pytest.fixture
def data(clear_fsspec_memory_cache):
    # the link table is instance state, shared via the fsspec instance cache
    SymlinkFileSystem.clear_instance_cache()
    UPath("memory:///data/v1/a.txt").write_text("v1")
    UPath("memory:///data/v2/a.txt").write_text("v2")
    UPath("memory:///data/v2/sub/b.txt").write_text("b")
    try:
        yield UPath("symlinks::memory://data", mapping=MAPPING)
    finally:
        SymlinkFileSystem.clear_instance_cache()


def test_is_correct_class(data):
    assert isinstance(data, SymlinkPath)
    assert isinstance(data.fs, SymlinkFileSystem)
    assert str(data) == "symlinks::memory:///data"
    assert data.path == "/data"


def test_derived_paths_keep_chain(data):
    child = data / "latest" / "a.txt"
    assert isinstance(child, SymlinkPath)
    assert str(child) == "symlinks::memory:///data/latest/a.txt"
    assert child.parent.parent == data
    assert child.fs is data.fs


def test_link_table_shared_between_instances(data):
    data.joinpath("new-link").symlink_to("v1")
    other = UPath("symlinks::memory://data/new-link", mapping=MAPPING)
    assert other.fs is data.fs
    assert other.is_symlink()


@pytest.mark.parametrize(
    "name,expected",
    [
        ("latest", True),
        ("current.txt", True),
        ("dangling", True),
        ("loop1", True),
        ("v1", False),
        ("latest/a.txt", False),
        ("does-not-exist", False),
    ],
)
def test_is_symlink(data, name, expected):
    assert data.joinpath(name).is_symlink() is expected
    assert data.joinpath(name).info.is_symlink() is expected


def test_readlink(data):
    assert data.joinpath("current.txt").readlink() == UPath(
        "symlinks::memory://data/v1/a.txt", mapping=MAPPING
    )
    relative = data.joinpath("latest").readlink()
    assert not relative.is_absolute()
    assert str(relative) == "v2"
    assert data.joinpath(relative).resolve() == data.joinpath("v2")
    with pytest.raises(OSError) as exc_info:
        data.joinpath("v1").readlink()
    assert exc_info.value.errno == errno.EINVAL


def test_resolve(data):
    assert data.joinpath("latest", "sub", "b.txt").resolve() == data.joinpath(
        "v2", "sub", "b.txt"
    )
    assert data.joinpath("up", "a.txt").resolve() == data.joinpath("v1", "a.txt")
    assert data.joinpath("latest", "..", "v1").resolve() == data.joinpath("v1")
    assert data.joinpath("dangling").resolve() == data.joinpath("missing")
    with pytest.raises(FileNotFoundError):
        data.joinpath("dangling").resolve(strict=True)
    with pytest.raises(OSError) as exc_info:
        data.joinpath("loop1").resolve()
    assert exc_info.value.errno == errno.ELOOP


def test_read_through_links(data):
    assert data.joinpath("latest", "a.txt").read_text() == "v2"
    assert data.joinpath("latest", "sub", "b.txt").read_text() == "b"
    assert data.joinpath("current.txt").read_text() == "v1"
    assert data.joinpath("up", "a.txt").read_bytes() == b"v1"
    with data.joinpath("current.txt").open("rb") as f:
        assert f.read() == b"v1"
    with pytest.raises(FileNotFoundError):
        data.joinpath("dangling").read_text()


def test_write_through_links(data):
    data.joinpath("current.txt").write_text("changed")
    assert UPath("memory:///data/v1/a.txt").read_text() == "changed"
    data.joinpath("latest", "new.txt").write_text("new")
    assert UPath("memory:///data/v2/new.txt").read_text() == "new"


def test_follow_symlinks_flags(data):
    latest = data.joinpath("latest")
    assert latest.exists()
    assert latest.is_dir()
    assert not latest.is_dir(follow_symlinks=False)
    assert latest.joinpath("a.txt").is_file()
    assert stat.S_ISDIR(latest.stat().st_mode)
    assert stat.S_ISLNK(latest.lstat().st_mode)
    dangling = data.joinpath("dangling")
    assert not dangling.exists()
    assert dangling.exists(follow_symlinks=False)
    assert not dangling.info.exists()
    assert dangling.info.exists(follow_symlinks=False)


def test_iterdir(data):
    assert sorted(p.name for p in data.iterdir()) == [
        "current.txt",
        "dangling",
        "latest",
        "loop1",
        "loop2",
        "up",
        "v1",
        "v2",
    ]
    assert sorted(data.joinpath("latest").iterdir()) == [
        data.joinpath("latest", "a.txt"),
        data.joinpath("latest", "sub"),
    ]


def test_glob_does_not_recurse_into_linked_dirs(data):
    assert sorted(str(p.relative_to(data)) for p in data.glob("**/*.txt")) == [
        "current.txt",
        "v1/a.txt",
        "v2/a.txt",
        "v2/sub/b.txt",
    ]
    assert sorted(p.name for p in data.glob("latest/*")) == ["a.txt", "sub"]


def test_walk_does_not_follow_symlinks(data):
    walked = {
        str(p.relative_to(data)): (sorted(dirs), sorted(files))
        for p, dirs, files in data.walk()
    }
    assert sorted(walked) == [".", "v1", "v2", "v2/sub"]
    assert walked["."][0] == ["v1", "v2"]
    assert "latest" in walked["."][1]


def test_symlink_to_and_unlink(data):
    link = data.joinpath("v1-link")
    link.symlink_to(data.joinpath("v1"))
    assert link.is_symlink()
    assert link.readlink() == data.joinpath("v1")
    assert link.joinpath("a.txt").read_text() == "v1"
    with pytest.raises(FileExistsError):
        link.symlink_to("v2")

    link.unlink()
    assert not link.exists(follow_symlinks=False)
    assert data.joinpath("v1", "a.txt").read_text() == "v1"


def test_symlink_in_implied_directory(data):
    link = data.joinpath("new", "dir", "link")
    link.symlink_to("../../v2")
    assert data.joinpath("new").is_dir()
    assert [p.name for p in data.joinpath("new").iterdir()] == ["dir"]
    assert link.joinpath("a.txt").read_text() == "v2"


def test_rename_link(data):
    target = data.joinpath("current.txt").rename(data.joinpath("renamed.txt"))
    assert target.is_symlink()
    assert target.read_text() == "v1"
    assert not data.joinpath("current.txt").exists(follow_symlinks=False)


def test_copy_preserves_symlinks(data):
    dst = UPath("symlinks::memory://copy", mapping={})
    data.joinpath("v2").copy(dst.joinpath("v2"))
    data.joinpath("latest").copy(dst.joinpath("latest"), follow_symlinks=False)
    assert dst.joinpath("latest").is_symlink()
    assert dst.joinpath("latest", "sub", "b.txt").read_text() == "b"


def test_copy_local_symlinks(data, tmp_path):
    local = tmp_path / "local"
    local.joinpath("real").mkdir(parents=True)
    local.joinpath("real", "f.txt").write_text("local")
    local.joinpath("link.txt").symlink_to("real/f.txt")

    dst = UPath("symlinks::memory://from-local", mapping={})
    UPath(local).copy(dst, follow_symlinks=False)
    assert dst.joinpath("link.txt").is_symlink()
    assert str(dst.joinpath("link.txt").readlink()) == "real/f.txt"
    assert dst.joinpath("link.txt").read_text() == "local"


def test_fsspec_level_api(data):
    fs = data.fs
    info = fs.info("/data/latest")
    assert info["type"] == "directory"
    assert info["islink"] is True
    assert info["destination"] == "v2"
    entries = {e["name"]: e for e in fs.ls("/data", detail=True)}
    assert entries["/data/latest"]["type"] == "other"
    assert entries["/data/v1"]["islink"] is False
    assert fs.cat_file("/data/latest/a.txt") == b"v2"
    assert fs.readlink("/data/latest") == "v2"


def test_fsspec_url_chaining(data):
    with fsspec.open(
        "symlinks::memory://data/latest/a.txt", "rt", symlinks={"mapping": MAPPING}
    ) as f:
        assert f.read() == "v2"


def test_filesystem_with_target_instance(data):
    fs = SymlinkFileSystem(fs=fsspec.filesystem("memory"), mapping={"/x": "/data/v2"})
    assert sorted(fs.ls("/x", detail=False)) == ["/x/a.txt", "/x/sub"]
