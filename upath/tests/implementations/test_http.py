import pytest  # noqa: F401
from fsspec import get_filesystem_class

from upath import UPath
from upath.implementations.http import HTTPPath

from ..cases import JoinablePathTests
from ..cases import NonWritablePathTests
from ..cases import ReadablePathTests
from ..utils import OverrideMeta
from ..utils import extends_base
from ..utils import overrides_base
from ..utils import skip_on_windows
from ..utils import xfail_if_no_ssl_connection

pytestmark = pytest.mark.network

try:
    get_filesystem_class("http")
except ImportError:
    pytestmark = pytest.mark.skip


@pytest.fixture
def internet_connection():
    import requests

    try:
        requests.get("http://example.com")
    except requests.exceptions.ConnectionError:
        pytest.xfail(reason="No internet connection")
    else:
        yield


def test_httppath(internet_connection):
    path = UPath("http://example.com")
    assert isinstance(path, HTTPPath)
    assert path.exists()


@xfail_if_no_ssl_connection
def test_httpspath(internet_connection):
    path = UPath("https://example.com")
    assert isinstance(path, HTTPPath)
    assert path.exists()


@skip_on_windows
class TestUPathHttp(
    JoinablePathTests,
    ReadablePathTests,
    NonWritablePathTests,
    metaclass=OverrideMeta,
):
    @pytest.fixture(autouse=True, scope="function")
    def path(self, http_fixture):
        self.path = UPath(http_fixture)

    @overrides_base
    def test_is_correct_class(self):
        assert isinstance(self.path, HTTPPath)

    @extends_base
    def test_work_at_root(self):
        assert "folder" in (f.name for f in self.path.parent.iterdir())

    @extends_base
    def test_resolve(self):
        # Also tests following redirects, because the test server issues a
        # 301 redirect for `http://127.0.0.1:8080/folder` to
        # `http://127.0.0.1:8080/folder/`
        assert str(self.path.resolve()).endswith("/")

    @overrides_base
    def test_info(self):
        # HTTPPath folders are files too

        p0 = self.path.joinpath("file1.txt")
        p1 = self.path.joinpath("folder1")

        assert p0.info.exists() is True
        assert p0.info.is_file() is True
        assert p0.info.is_dir() is False
        assert p0.info.is_symlink() is False
        assert p1.info.exists() is True
        assert (
            p1.info.is_file() is True
        )  # Weird quirk of how directories work in http fsspec
        assert p1.info.is_dir() is True
        assert p1.info.is_symlink() is False


@pytest.mark.parametrize(
    "args,parts",
    [
        (("http://example.com/"), ("http://example.com/", "")),
        (("http://example.com//"), ("http://example.com/", "", "")),
        (("http://example.com///"), ("http://example.com/", "", "", "")),
        (("http://example.com/a"), ("http://example.com/", "a")),
        (("http://example.com/a/"), ("http://example.com/", "a", "")),
        (("http://example.com/a/b"), ("http://example.com/", "a", "b")),
        (("http://example.com/a//b"), ("http://example.com/", "a", "", "b")),
        (("http://example.com/a//b/"), ("http://example.com/", "a", "", "b", "")),
    ],
)
def test_empty_parts(args, parts):
    pth = UPath(args)
    pth_parts = pth.parts
    assert pth_parts == parts


def test_query_parameters_passthrough():
    pth = UPath("http://example.com/?a=1&b=2")
    assert str(pth) == "http://example.com/?a=1&b=2"
    assert pth.path == "http://example.com/?a=1&b=2"
    assert pth.parts == ("http://example.com/", "")
    assert pth.query == {"a": "1", "b": "2"}


@pytest.mark.parametrize(
    "urlpath,query,fragment",
    [
        ("http://example.com/a.txt", {}, ""),
        ("http://example.com/a.txt?x=1&y=", {"x": "1", "y": ""}, ""),
        ("http://example.com/a.txt?x=1&x=2", {"x": "1"}, ""),
        ("http://example.com/a.txt?q=a+b%2Bc%26", {"q": "a b+c&"}, ""),
        ("http://example.com/a.txt#sec%201", {}, "sec 1"),
        ("https://example.com/a.txt?x=1#frag", {"x": "1"}, "frag"),
    ],
)
def test_query_and_fragment(urlpath, query, fragment):
    pth = UPath(urlpath)
    assert pth.query == query
    assert pth.fragment == fragment
    assert str(pth) == urlpath


@pytest.mark.parametrize(
    "urlpath",
    [
        "http://example.com/dir/file.txt",
        "http://example.com/dir/file.txt?x=1&y=2",
        "http://example.com/dir/file.txt#frag",
        "http://example.com/dir/file.txt?x=1#frag",
    ],
)
def test_query_and_fragment_not_part_of_name(urlpath):
    pth = UPath(urlpath)
    assert pth.name == "file.txt"
    assert pth.stem == "file"
    assert pth.suffix == ".txt"
    assert pth.parts == ("http://example.com/", "dir", "file.txt")


@pytest.mark.parametrize(
    "transform,expected",
    [
        (lambda p: p / "x", "http://example.com/dir/file.txt/x"),
        (lambda p: p.joinpath("x", "y"), "http://example.com/dir/file.txt/x/y"),
        (lambda p: p.joinpath("x?z=3"), "http://example.com/dir/file.txt/x?z=3"),
        (lambda p: UPath(p, "x"), "http://example.com/dir/file.txt/x"),
        (lambda p: p.parent, "http://example.com/dir"),
        (lambda p: p.with_name("y.csv"), "http://example.com/dir/y.csv"),
        (lambda p: p.with_stem("y"), "http://example.com/dir/y.txt"),
        (lambda p: p.with_suffix(".csv"), "http://example.com/dir/file.csv"),
    ],
)
def test_query_and_fragment_dropped_by_path_operations(transform, expected):
    pth = UPath("http://example.com/dir/file.txt?x=1&y=2#frag")
    assert str(transform(pth)) == expected


def test_query_and_fragment_preserved_by_resolve():
    pth = UPath("http://example.com/a/./b/../c?x=1#frag")
    resolved = pth.resolve(follow_redirects=False)
    assert str(resolved) == "http://example.com/a/c?x=1#frag"


@pytest.mark.parametrize(
    "query,params,expected",
    [
        (None, {}, "http://example.com/a.txt#frag"),
        ("", {}, "http://example.com/a.txt#frag"),
        ({}, {}, "http://example.com/a.txt#frag"),
        (None, {"b": "2"}, "http://example.com/a.txt?b=2#frag"),
        (None, {"b": 2, "c": 1.5}, "http://example.com/a.txt?b=2&c=1.5#frag"),
        ({"q": "a b&ä"}, {}, "http://example.com/a.txt?q=a+b%26%C3%A4#frag"),
        ([("b", "1"), ("b", "2")], {}, "http://example.com/a.txt?b=1&b=2#frag"),
        ("sig=ab%2Fcd&b", {}, "http://example.com/a.txt?sig=ab%2Fcd&b#frag"),
        ("?b=2", {}, "http://example.com/a.txt?b=2#frag"),
    ],
)
def test_with_query(query, params, expected):
    pth = UPath("http://example.com/a.txt?x=1#frag")
    assert str(pth.with_query(query, **params)) == expected


@pytest.mark.parametrize(
    "query,params,exc",
    [
        ({"a": "1"}, {"b": "2"}, ValueError),
        ("a=1#b", {}, ValueError),
        ({"a": True}, {}, TypeError),
        (None, {"a": None}, TypeError),
    ],
)
def test_with_query_errors(query, params, exc):
    pth = UPath("http://example.com/a.txt")
    with pytest.raises(exc):
        pth.with_query(query, **params)


@pytest.mark.parametrize(
    "fragment,expected",
    [
        (None, "http://example.com/a.txt?x=1"),
        ("", "http://example.com/a.txt?x=1"),
        ("intro", "http://example.com/a.txt?x=1#intro"),
        ("sec 1/a?b", "http://example.com/a.txt?x=1#sec%201/a?b"),
        ("100%", "http://example.com/a.txt?x=1#100%25"),
    ],
)
def test_with_fragment(fragment, expected):
    pth = UPath("http://example.com/a.txt?x=1#frag")
    new = pth.with_fragment(fragment)
    assert str(new) == expected
    assert new.fragment == (fragment or "")
    assert new.query == {"x": "1"}


@pytest.mark.parametrize(
    "base,rel,expected",
    [
        (
            "http://www.example.com/a/b/index.html",
            "image.png?version=1",
            "http://www.example.com/a/b/image.png?version=1",
        ),
        (
            "http://www.example.com/a/b/index.html",
            "../image.png",
            "http://www.example.com/a/image.png",
        ),
        (
            "http://www.example.com/a/b/index.html",
            "/image.png",
            "http://www.example.com/image.png",
        ),
        (
            "http://www.example.com/a/b/index.html",
            "sftp://other.com/image.png",
            "sftp://other.com/image.png",
        ),
        (
            "http://www.example.com/a/b/index.html",
            "//other.com/image.png",
            "http://other.com/image.png",
        ),
    ],
)
def test_joinuri_behavior(base, rel, expected):
    p0 = UPath(base)
    pr = p0.joinuri(rel)
    pe = UPath(expected)
    assert pr == pe


NORMALIZATIONS = (
    ("unnormalized", "normalized"),
    (
        # Expected normalization results according to curl
        ("http://example.com", "http://example.com/"),
        ("http://example.com/", "http://example.com/"),
        ("http://example.com/a", "http://example.com/a"),
        ("http://example.com//a", "http://example.com//a"),
        ("http://example.com///a", "http://example.com///a"),
        ("http://example.com////a", "http://example.com////a"),
        ("http://example.com/a/.", "http://example.com/a/"),
        ("http://example.com/a/./", "http://example.com/a/"),
        ("http://example.com/a/./b", "http://example.com/a/b"),
        ("http://example.com/a/.//", "http://example.com/a//"),
        ("http://example.com/a/.//b", "http://example.com/a//b"),
        ("http://example.com/a//.", "http://example.com/a//"),
        ("http://example.com/a//./", "http://example.com/a//"),
        ("http://example.com/a//./b", "http://example.com/a//b"),
        ("http://example.com/a//.//", "http://example.com/a///"),
        ("http://example.com/a//.//b", "http://example.com/a///b"),
        ("http://example.com/a/..", "http://example.com/"),
        ("http://example.com/a/../", "http://example.com/"),
        ("http://example.com/a/../.", "http://example.com/"),
        ("http://example.com/a/../..", "http://example.com/"),
        ("http://example.com/a/../../", "http://example.com/"),
        ("http://example.com/a/../..//", "http://example.com//"),
        ("http://example.com/a/..//", "http://example.com//"),
        ("http://example.com/a/..//.", "http://example.com//"),
        ("http://example.com/a/..//..", "http://example.com/"),
        ("http://example.com/a/../b", "http://example.com/b"),
        ("http://example.com/a/..//b", "http://example.com//b"),
        ("http://example.com/a//..", "http://example.com/a/"),
        ("http://example.com/a//../", "http://example.com/a/"),
        ("http://example.com/a//../.", "http://example.com/a/"),
        ("http://example.com/a//../..", "http://example.com/"),
        ("http://example.com/a//../../", "http://example.com/"),
        ("http://example.com/a//../..//", "http://example.com//"),
        ("http://example.com/a//..//..", "http://example.com/a/"),
        ("http://example.com/a//../b", "http://example.com/a/b"),
        ("http://example.com/a//..//", "http://example.com/a//"),
        ("http://example.com/a//..//.", "http://example.com/a//"),
        ("http://example.com/a//..//b", "http://example.com/a//b"),
    ),
)


@pytest.mark.parametrize(*NORMALIZATIONS)
def test_normalize(unnormalized, normalized):
    expected = HTTPPath(normalized)
    pth = HTTPPath(unnormalized)
    assert expected.protocol in {"http", "https"}
    assert pth.protocol in {"http", "https"}

    # Normalise only, do not attempt to follow redirects for http:// paths here
    result = pth.resolve(strict=True, follow_redirects=False)

    str_expected = str(expected)
    str_result = str(result)
    assert expected == result
    assert str_expected == str_result
