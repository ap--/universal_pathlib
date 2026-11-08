"""Tests for the public parser API in `upath.parsers` (see #291)."""

from __future__ import annotations

import pytest
from fsspec.implementations.memory import MemoryFileSystem
from fsspec.registry import _registry as fsspec_class_registry
from fsspec.spec import AbstractFileSystem
from fsspec.utils import infer_storage_options

from upath import UPath
from upath._flavour import WrappedFileSystemFlavour
from upath._flavour import upath_strip_protocol
from upath._flavour_sources import AbstractFileSystemFlavour
from upath._flavour_sources import flavour_registry
from upath.implementations.cloud import S3Path
from upath.parsers import FSSpecParser

from .utils import temporary_register


class ArrowLikeFileSystem(AbstractFileSystem):
    """mimics the parsing API of fsspec's ArrowFSWrapper

    The protocol is a property and `_parent` is an instance method,
    so they can't be used without instantiating the filesystem.
    """

    root_marker = "/"

    @property
    def protocol(self):
        return "arrowlike"

    def _parent(self, path):
        path = self._strip_protocol(path).lstrip("/")
        return path.rsplit("/", 1)[0] if "/" in path else ""

    @classmethod
    def _strip_protocol(cls, path):
        path = infer_storage_options(path)["path"]
        if path.startswith("//"):
            path = path[1:]
        return path


class FooFileSystem(ArrowLikeFileSystem):
    """the custom s3-like filesystem from #291"""

    protocol = "foo"

    @classmethod
    def _strip_protocol(cls, path):
        storage_opts = infer_storage_options(path)
        if host := storage_opts.get("host"):
            storage_opts["path"] = host + storage_opts["path"]
        path_without_protocol = str(storage_opts["path"])
        if path_without_protocol.startswith("//"):
            path_without_protocol = path_without_protocol[1:]
        return path_without_protocol


@pytest.fixture
def restore_flavour_registry():
    saved = dict(flavour_registry)
    try:
        yield
    finally:
        flavour_registry.clear()
        flavour_registry.update(saved)
        WrappedFileSystemFlavour.from_protocol.cache_clear()


def _parser_from_filesystem_class():
    return FSSpecParser(
        FooFileSystem,
        root_marker="",
        netloc_is_anchor=True,
        supports_empty_parts=True,
    )


def _parser_like_s3():
    return FSSpecParser("s3", protocol="foo")


def _parser_legacy_workaround():
    # the workaround posted in #291, using private APIs
    class FooFileSystemFlavour(AbstractFileSystemFlavour):
        protocol = "foo"
        root_marker = ""
        sep = "/"

    return WrappedFileSystemFlavour(
        FooFileSystemFlavour, netloc_is_anchor=True, supports_empty_parts=True
    )


@pytest.fixture(
    params=[
        _parser_from_filesystem_class,
        _parser_like_s3,
        _parser_legacy_workaround,
    ],
    ids=["filesystem-class", "like-s3", "legacy-workaround"],
)
def foo_path_cls(request, monkeypatch, restore_flavour_registry):
    class FooPath(S3Path):
        parser = request.param()

    monkeypatch.setitem(fsspec_class_registry, "foo", FooFileSystem)
    with temporary_register("foo", FooPath):
        yield FooPath


@pytest.mark.parametrize(
    "path",
    [
        "bucket",
        "bucket/",
        "bucket/a",
        "bucket/a/",
        "bucket/a/b.txt",
        "bucket/a//b.txt",
        "bucket/a/../b",
    ],
)
def test_foo_path_behaves_like_s3_path(foo_path_cls, path):
    foo = UPath(f"foo://{path}")
    s3 = UPath(f"s3://{path}")
    assert type(foo) is foo_path_cls

    assert foo.path == s3.path
    assert foo.parts == s3.parts
    assert (foo.drive, foo.root, foo.anchor) == (s3.drive, s3.root, s3.anchor)
    assert foo.name == s3.name
    assert foo.is_absolute() is s3.is_absolute()
    assert foo.parent.path == s3.parent.path
    assert [p.path for p in foo.parents] == [p.path for p in s3.parents]
    assert foo.resolve().path == s3.resolve().path
    for segment in ["c", "/c", "c//d", "c/", ""]:
        assert (foo / segment).path == (s3 / segment).path
        assert (
            UPath(f"foo://{path}", segment).path == UPath(f"s3://{path}", segment).path
        )
    assert UPath(str(foo)) == foo


def test_foo_path_without_custom_parser_fails(monkeypatch):
    class FooPath(S3Path):
        pass

    monkeypatch.setitem(fsspec_class_registry, "foo", FooFileSystem)
    with temporary_register("foo", FooPath):
        with pytest.raises(ValueError, match="bucket/container missing"):
            UPath("foo://bucket/a")


def test_registered_parser_is_used_for_protocol(foo_path_cls):
    assert WrappedFileSystemFlavour.from_protocol("foo") is foo_path_cls.parser
    assert upath_strip_protocol("foo://bucket/a") == "bucket/a"


def test_registered_parser_for_other_protocol_warns():
    class BarPath(S3Path):
        parser = FSSpecParser("s3")

    with temporary_register("bar", BarPath):
        with pytest.warns(UserWarning, match="protocol='bar'"):
            WrappedFileSystemFlavour.from_protocol("bar")


def test_registered_parser_is_used_in_chains(foo_path_cls):
    p = UPath("zip://file.txt::foo://bucket/archive.zip")
    assert p.storage_options["target_protocol"] == "foo"
    assert p.storage_options["fo"] == "bucket/archive.zip"


def test_custom_parser_for_builtin_protocol():
    class StrictS3Path(S3Path):
        parser = FSSpecParser("s3", supports_empty_parts=False)

    assert UPath("s3://bucket/a", "/c").path == "bucket/a//c"
    with temporary_register("s3", StrictS3Path):
        p = UPath("s3://bucket/a")
        assert isinstance(p, StrictS3Path)
        assert UPath("s3://bucket/a", "/c").path == "bucket/c"
        assert (p / "/c").path == "bucket/c"
    assert UPath("s3://bucket/a", "/c").path == "bucket/a//c"


@pytest.mark.parametrize("protocol", ["s3", "gcs", "az", "https", "memory", "sftp"])
def test_protocol_parser_defaults(protocol):
    default = WrappedFileSystemFlavour.from_protocol(protocol)
    parser = FSSpecParser(protocol)
    assert parser.protocol == default.protocol
    assert parser.root_marker == default.root_marker
    assert parser.netloc_is_anchor is default.netloc_is_anchor
    assert parser.supports_empty_parts is default.supports_empty_parts
    assert parser.has_meaningful_trailing_slash is default.has_meaningful_trailing_slash
    uri = f"{protocol}://host/a/b"
    assert parser.strip_protocol(uri) == default.strip_protocol(uri)
    assert parser.splitroot(uri) == default.splitroot(uri)


def test_protocol_is_resolved_lazily(monkeypatch):
    class LazyFileSystem(AbstractFileSystem):
        protocol = "lazyproto"

        @classmethod
        def _strip_protocol(cls, path):
            return "/resolved/" + super()._strip_protocol(path)

    parser = FSSpecParser("lazyproto")
    monkeypatch.setitem(fsspec_class_registry, "lazyproto", LazyFileSystem)
    assert parser.strip_protocol("lazyproto://a/b") == "/resolved/a/b"
    assert parser.protocol == ("lazyproto",)


def test_unknown_protocol_uses_generic_parser():
    parser = FSSpecParser("unknownproto")
    assert parser.protocol == ("unknownproto",)
    assert parser.strip_protocol("unknownproto://a/b/") == "a/b"
    assert parser.join("a", "b") == "a/b"


def test_filesystem_parsing_api_on_instance_level():
    parser = FSSpecParser(ArrowLikeFileSystem, protocol="arrowlike")
    assert parser.protocol == ("arrowlike",)
    assert parser.root_marker == "/"
    assert parser.parent("arrowlike:///a/b") == "/a"
    assert parser.split("arrowlike:///a/b") == ("/a", "b")


def test_defaults_are_taken_from_spec():
    class HTTPLikeFileSystem(AbstractFileSystem):
        protocol = ("http", "https")

    parser = FSSpecParser(HTTPLikeFileSystem, protocol="foo")
    assert parser.protocol == ("foo",)
    assert parser.netloc_is_anchor is True
    assert parser.has_meaningful_trailing_slash is True
    parser = FSSpecParser(FooFileSystem)
    assert parser.netloc_is_anchor is False
    assert parser.supports_empty_parts is False


def test_filesystem_without_protocol_class_attribute():
    with pytest.raises(TypeError, match="protocol"):
        FSSpecParser(ArrowLikeFileSystem)


@pytest.mark.parametrize("spec", [123, MemoryFileSystem(), AbstractFileSystemFlavour])
def test_invalid_spec(spec):
    with pytest.raises(TypeError):
        FSSpecParser(spec)


def test_root_marker_override_is_used_consistently():
    parser = FSSpecParser(FooFileSystem, root_marker="")
    assert parser.root_marker == ""
    assert parser.strip_protocol("foo://") == ""
    assert parser.parent("foo://bucket/a") == "bucket"
    assert parser.parent("foo://bucket") == ""
    assert parser.isabs("foo://bucket/a")


def test_protocol_override_does_not_register_flavour(restore_flavour_registry):
    parser = FSSpecParser("s3", protocol="notregistered")
    assert parser.protocol == ("notregistered",)
    assert parser.strip_protocol("notregistered://bucket/a") == "bucket/a"
    assert "notregistered" not in flavour_registry
    # creating it twice must not raise
    FSSpecParser("s3", protocol="notregistered").protocol


def test_instance_level_parent_of_registered_filesystem(monkeypatch):
    # ArrowFSWrapper based filesystems, i.e. hdfs, implement _parent as an
    # instance method. This must not break UPath once fsspec imported them.
    pytest.importorskip("fsspec.implementations.arrow")
    from fsspec.implementations.arrow import HadoopFileSystem

    monkeypatch.setitem(fsspec_class_registry, "hdfs", HadoopFileSystem)
    WrappedFileSystemFlavour.from_protocol.cache_clear()
    try:
        p = UPath("hdfs:///a/b")
        assert p.parent.path == "/a"
        assert p.parts == ("/", "a", "b")
    finally:
        WrappedFileSystemFlavour.from_protocol.cache_clear()


def test_repr():
    assert repr(FSSpecParser("s3", protocol="foo")) == (
        "FSSpecParser('s3', protocol='foo', netloc_is_anchor=True,"
        " supports_empty_parts=True, meaningful_trailing_slash=False)"
    )
    assert repr(FSSpecParser(FooFileSystem)).startswith("FSSpecParser(FooFileSystem,")


def test_default_parser_unchanged():
    parser = UPath("s3://bucket/a").parser
    assert type(parser) is WrappedFileSystemFlavour
    assert repr(parser).startswith("<wrapped class S3FileSystem")
