import pathlib
import pickle
import sys
import warnings

import pytest

from upath import UPath
from upath.core import PosixUPath
from upath.implementations.cloud import GCSPath
from upath.implementations.cloud import S3Path

from .cases import BaseTests
from .utils import exact_equal
from .utils import only_on_windows
from .utils import skip_on_windows


@skip_on_windows
def test_posix_path(local_testdir):
    assert isinstance(UPath(local_testdir), pathlib.PosixPath)


@only_on_windows
def test_windows_path(local_testdir):
    assert isinstance(UPath(local_testdir), pathlib.WindowsPath)


def test_UPath_untested_protocol_warning(clear_registry):
    with warnings.catch_warnings(record=True) as w:
        _ = UPath("mock:///")
    assert len(w) == 1
    assert issubclass(w[-1].category, UserWarning)
    assert "mock" in str(w[-1].message)


def test_UPath_file_protocol_no_warning():
    with warnings.catch_warnings(record=True) as w:
        _ = UPath("file:/")
        assert len(w) == 0


class TestUpath(BaseTests):
    @pytest.fixture(autouse=True)
    def path(self, local_testdir):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # On Windows the path needs to be prefixed with `/`, because
            # `UPath` implements `_posix_flavour`, which requires a `/` root
            # in order to correctly deserialize pickled objects
            root = "/" if sys.platform.startswith("win") else ""
            self.path = UPath(f"mock://{root}{local_testdir}")

    def test_fsspec_compat(self):
        pass


@pytest.mark.hdfs
def test_multiple_backend_paths(local_testdir, s3_fixture, hdfs):
    _, anon, s3so = s3_fixture
    path = f"s3:{local_testdir}"
    s3_path = UPath(path, anon=anon, **s3so)
    assert s3_path.joinpath("text.txt")._url.scheme == "s3"
    host, user, port = hdfs
    path = f"hdfs:{local_testdir}"
    UPath(path, host=host, user=user, port=port)
    assert s3_path.joinpath("text1.txt")._url.scheme == "s3"


def test_constructor_accept_path(local_testdir):
    path = UPath(pathlib.Path(local_testdir))
    assert str(path) == str(pathlib.Path(local_testdir))


def test_constructor_accept_upath(local_testdir):
    path = UPath(UPath(local_testdir))
    assert str(path) == str(pathlib.Path(local_testdir))


def test_subclass(local_testdir):
    class MyPath(UPath):
        pass

    path = MyPath(local_testdir)
    assert str(path) == str(pathlib.Path(local_testdir))
    assert issubclass(MyPath, UPath)
    assert isinstance(path, pathlib.Path)


def test_subclass_with_gcs():
    path = UPath("gcs://bucket", storage_options={"anon": True})
    assert isinstance(path, UPath)
    assert isinstance(path, pathlib.Path)


def test_instance_check(local_testdir):
    path = pathlib.Path(local_testdir)
    upath = UPath(local_testdir)
    # test instance check passes
    assert isinstance(upath, pathlib.Path)
    assert isinstance(upath, UPath)
    # test type is same as pathlib
    assert issubclass(type(upath), type(path))
    upath = UPath(f"file://{local_testdir}")
    # test default implementation is used
    assert issubclass(type(upath), UPath)


def test_new_method(local_testdir):
    assert isinstance(pathlib.Path(local_testdir), pathlib.Path)
    assert isinstance(UPath(local_testdir), pathlib.Path)
    assert isinstance(UPath(local_testdir), UPath)


@skip_on_windows
class TestFSSpecLocal(BaseTests):
    @pytest.fixture(autouse=True)
    def path(self, local_testdir):
        path = f"file://{local_testdir}"
        self.path = UPath(path)


PATHS = (
    ("path", "storage_options", "object_type"),
    (
        ("/tmp/abc", (), pathlib.Path),
        ("s3://bucket/folder", ({"anon": True}), S3Path),
        ("gs://bucket/folder", ({"token": "anon"}), GCSPath),
    ),
)


@pytest.mark.parametrize(*PATHS)
def test_create_from_type(path, storage_options, object_type):
    """Test that derived paths use same fs instance."""
    if storage_options:
        upath = UPath(path, storage_options=storage_options)
    else:
        upath = UPath(path)

    # test expected object type
    assert isinstance(upath, object_type)
    cast = type(upath)
    parent = upath.parent
    # test derived object is same type
    assert isinstance(parent, cast)
    new = cast(str(parent))
    # test that object cast is same type
    assert isinstance(new, cast)


def test_list_args():
    path_a = UPath("gcs://bucket", "folder")
    path_b = UPath("gcs://bucket") / "folder"

    assert exact_equal(path_a, path_b)


def test_child_path():
    path_a = UPath("gcs://bucket/folder")
    path_b = UPath("gcs://bucket") / "folder"

    assert exact_equal(path_a, path_b)


def test_pickling():
    path = UPath("gcs://bucket/folder", storage_options={"anon": True})
    pickled_path = pickle.dumps(path)
    recovered_path = pickle.loads(pickled_path)

    assert exact_equal(path, recovered_path)


def test_pickling_child_path():
    path = (
        UPath("gcs://bucket", storage_options={"anon": True})
        / "subfolder"
        / "subsubfolder"
    )
    pickled_path = pickle.dumps(path)
    recovered_path = pickle.loads(pickled_path)

    assert exact_equal(path, recovered_path)


def test_copy_path():
    path = UPath("gcs://bucket/folder", storage_options={"anon": True})
    copy_path = UPath(path)

    assert exact_equal(path, copy_path)


@skip_on_windows
def test_copy_path_posix():
    path = PosixUPath("/tmp/folder")
    copy_path = UPath(path)

    assert exact_equal(path, copy_path)


def test_copy_path_append():
    path = UPath("/tmp/folder")
    copy_path = UPath(path, "folder2")

    assert type(path) == type(copy_path)
    assert str(path / "folder2") == str(copy_path)

    path = UPath("/tmp/folder")
    copy_path = UPath(path, "folder2/folder3")

    assert str(path / "folder2" / "folder3") == str(copy_path)

    path = UPath("/tmp/folder")
    copy_path = UPath(path, "folder2", "folder3")

    assert str(path / "folder2" / "folder3") == str(copy_path)


def test_copy_path_append_kwargs():
    path = UPath("gcs://bucket/folder", storage_options={"anon": True})
    copy_path = UPath(path, storage_options={"anon": False})

    assert type(path) == type(copy_path)
    assert str(path) == str(copy_path)
    assert not copy_path._storage_options["anon"]
    assert path._storage_options["anon"]


def test_relative_to_same_fs():
    p0 = UPath("s3://test_bucket/file.txt")
    p1 = UPath("s3://test_bucket")
    assert "s3://test_bucket/file.txt" == str(p0.relative_to(p1))


def test_relative_to_different_fs():
    p0 = UPath("s3://test_bucket/file.txt")
    p1 = UPath("gcs://test_bucket")
    with pytest.raises(ValueError):
        p0.relative_to(p1)


def test_relative_to_different_storage_options():
    p0 = UPath("s3://test_bucket/file.txt", storage_options={"anon": True})
    p1 = UPath("s3://test_bucket/file.txt", storage_options={"anon": False})
    with pytest.raises(ValueError):
        p0.relative_to(p1)


def test_init_deprecated_storage_options_as_kw():
    with pytest.deprecated_call(match="^please provide filesystem storage options"):
        UPath("s3://test_bucket/file.txt", anon=True)


NORMALIZATIONS = (
    ("unnormalized", "normalized"),
    (
        ("file:///a/b/", "file:///a/b"),
        ("file:///a/b/..", "file:///a/"),
        ("file:///a/b/../..", "file:///"),
        ("file:///a/b/../../..", "file:///"),
    ),
)


@pytest.mark.parametrize(*NORMALIZATIONS)
def test_normalize(unnormalized, normalized):
    expected = str(UPath(normalized))
    result = str(UPath.resolve(UPath(unnormalized)))
    assert expected == result
