import copy
import io
import pickle
import zipfile
from collections.abc import Mapping

import fsspec
import pytest
from fsspec.core import url_to_fs

from upath import UPath
from upath.extensions import ProxyUPath
from upath.types import StorageOptions


@pytest.fixture
def memory_files(clear_fsspec_memory_cache):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("file.txt", b"zipped")
    fs = fsspec.filesystem("memory")
    fs.pipe("/so-tests/file.txt", b"hello")
    fs.pipe("/so-tests/archive.zip", buf.getvalue())
    yield


@pytest.fixture
def local_zip(tmp_path):
    pth = tmp_path.joinpath("archive.zip")
    with zipfile.ZipFile(pth, "w") as zf:
        zf.writestr("file.txt", b"zipped")
    return pth


# === mapping behavior ================================================


def test_storage_options_type():
    p = UPath("memory:///a/b", skip_instance_cache=True)
    so = p.storage_options
    assert isinstance(so, StorageOptions)
    assert isinstance(so, Mapping)
    assert not isinstance(so, dict)
    assert so.protocol == "memory"


def test_storage_options_mapping_interface():
    so = UPath("memory:///a/b", skip_instance_cache=True).storage_options
    assert so == {"skip_instance_cache": True}
    assert {"skip_instance_cache": True} == so
    assert so != {"skip_instance_cache": False}
    assert dict(so) == {"skip_instance_cache": True}
    assert dict(**so) == {"skip_instance_cache": True}
    assert len(so) == 1
    assert list(so) == ["skip_instance_cache"]
    assert "skip_instance_cache" in so
    assert "other" not in so
    assert so["skip_instance_cache"] is True
    assert so.get("other", 1) == 1
    assert list(so.keys()) == ["skip_instance_cache"]
    assert list(so.values()) == [True]
    assert list(so.items()) == [("skip_instance_cache", True)]


def test_storage_options_is_read_only():
    so = UPath("memory:///a/b", skip_instance_cache=True).storage_options
    with pytest.raises(TypeError):
        so["skip_instance_cache"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        del so["skip_instance_cache"]  # type: ignore[attr-defined]
    assert not hasattr(so, "update")
    assert not hasattr(so, "pop")
    with pytest.raises(AttributeError):
        so.some_attribute = 1  # type: ignore[attr-defined]


def test_storage_options_not_hashable():
    with pytest.raises(TypeError):
        hash(StorageOptions({}, protocol="memory"))


def test_storage_options_copies_input():
    options = {"a": 1}
    so = StorageOptions(options, protocol="memory")
    options["a"] = 2
    assert so == {"a": 1}


def test_storage_options_constructor():
    assert StorageOptions(protocol="memory") == {}
    assert StorageOptions(None, protocol="memory") == {}
    with pytest.raises(TypeError):
        StorageOptions({"a": 1})  # type: ignore[call-arg]


def test_storage_options_equality_ignores_protocol():
    # StorageOptions behaves like a read-only dict
    a = StorageOptions({"a": 1}, protocol="memory")
    b = StorageOptions({"a": 1}, protocol="file")
    assert a == b
    assert a != StorageOptions({"a": 2}, protocol="memory")
    assert a != [("a", 1)]


def test_storage_options_mappingproxy_compatibility():
    so = StorageOptions({"a": 1, "b": 2}, protocol="memory")
    c = so.copy()
    assert type(c) is dict
    assert c == {"a": 1, "b": 2}
    assert list(reversed(so)) == ["b", "a"]
    assert so | {"b": 3} == {"a": 1, "b": 3}
    assert type(so | {"b": 3}) is dict
    assert {"b": 3, "c": 4} | so == {"a": 1, "b": 2, "c": 4}
    assert type({"b": 3} | so) is dict
    with pytest.raises(TypeError):
        so | 1  # type: ignore[operator]


@pytest.mark.parametrize("protocol", [pickle.HIGHEST_PROTOCOL, 2])
def test_storage_options_pickle(protocol):
    so = StorageOptions({"a": {"b": 1}}, protocol="memory")
    so2 = pickle.loads(pickle.dumps(so, protocol=protocol))
    assert type(so2) is StorageOptions
    assert so2 == so
    assert so2.protocol == "memory"


def test_storage_options_copy():
    so = StorageOptions({"a": {"b": 1}}, protocol="memory")
    so_copy = copy.copy(so)
    so_deepcopy = copy.deepcopy(so)
    assert so_copy == so and so_copy.protocol == so.protocol
    assert so_deepcopy == so and so_deepcopy.protocol == so.protocol
    assert so_deepcopy["a"] is not so["a"]


def test_upath_still_works_with_storage_options():
    p = UPath("memory:///a/b", skip_instance_cache=True)
    assert p == UPath("memory:///a/b", **p.storage_options)
    assert p == pickle.loads(pickle.dumps(p))
    assert p != UPath("memory:///a/b")
    assert p.joinpath("c").storage_options == p.storage_options


def test_local_storage_options(tmp_path):
    p = UPath(tmp_path)
    assert isinstance(p.storage_options, StorageOptions)
    assert p.storage_options.protocol == ""
    assert p.storage_options == {}

    p = UPath(tmp_path.as_uri(), auto_mkdir=True)
    assert isinstance(p.storage_options, StorageOptions)
    assert p.storage_options.protocol == "file"
    assert p.storage_options == {"auto_mkdir": True}


def test_proxy_upath_storage_options():
    p = ProxyUPath("memory:///a/b", skip_instance_cache=True)
    assert isinstance(p.storage_options, StorageOptions)
    assert p.storage_options.protocol == "memory"
    assert p.storage_options == {"skip_instance_cache": True}


def test_simplecache_storage_options():
    p = UPath("simplecache::memory:///a/b", same_names=True)
    so = p.storage_options
    assert isinstance(so, StorageOptions)
    assert so.protocol == "simplecache"
    assert so == {
        "same_names": True,
        "target_protocol": "memory",
        "target_options": {},
    }


# === repr ============================================================


def test_repr_short():
    so = UPath("s3://bucket/key", anon=True).storage_options
    assert repr(so) == "StorageOptions({'anon': True}, protocol='s3')"


def test_repr_long_is_pretty_and_evaluable():
    so = UPath(
        "simplecache::memory:///a/b",
        same_names=True,
        memory={"skip_instance_cache": True},
    ).storage_options
    r = repr(so)
    assert r == (
        "StorageOptions(\n"
        "    {'same_names': True,\n"
        "     'target_options': {'skip_instance_cache': True},\n"
        "     'target_protocol': 'memory'},\n"
        "    protocol='simplecache',\n"
        ")"
    )
    so2 = eval(r, {"StorageOptions": StorageOptions})  # nosec B307
    assert so2 == so
    assert so2.protocol == so.protocol


@pytest.mark.parametrize(
    "options,secrets",
    [
        ({"key": "AKID1234", "secret": "s3cr3t", "token": "t0k3n"}, 3),
        ({"username": "user", "password": "pa55word"}, 1),
        ({"client_kwargs": {"aws_secret_access_key": "s3cr3t"}}, 1),
        ({"account_name": "acct", "account_key": "s3cr3t"}, 1),
        ({"sas_token": "?sv=1&sig=s3cr3t"}, 1),
        ({"connection_string": "AccountName=a;AccountKey=s3cr3t"}, 1),
        ({"client_secret": "s3cr3t", "credential": "s3cr3t"}, 2),
        ({"token": {"type": "service_account", "private_key": "s3cr3t"}}, 1),
        ({"target_options": {"password": "s3cr3t"}, "target_protocol": "ftp"}, 1),
    ],
)
def test_repr_redacts_secrets(options, secrets):
    so = StorageOptions(options, protocol="xyz")
    r = repr(so)
    for secret in ("AKID1234", "s3cr3t", "t0k3n", "pa55word"):
        assert secret not in r
    assert r.count("'***'") == secrets
    # values are still accessible
    assert dict(so) == options


@pytest.mark.parametrize(
    "options",
    [
        {"anon": True},
        {"token": "anon"},
        {"token": "google_default"},
        {"token": None},
        {"key": None},
        {"endpoint_url": "https://example.com", "account_name": "acct"},
        {"use_listings_cache": False, "username": "user"},
    ],
)
def test_repr_keeps_non_secrets(options):
    so = StorageOptions(options, protocol="xyz")
    assert "***" not in repr(so)
    assert eval(repr(so), {"StorageOptions": StorageOptions}) == so  # nosec B307


def test_relative_to_error_does_not_leak_secrets():
    a = UPath("memory:///a/b", password="s3cr3t")
    b = UPath("memory:///a", password="other")
    with pytest.raises(ValueError, match="incompatible storage_options") as e:
        a.relative_to(b)
    assert "s3cr3t" not in str(e.value)


# === to_unchained ====================================================

UNCHAINED_CASES = [
    pytest.param(
        "memory:///so-tests/file.txt",
        {},
        {},
        id="memory",
    ),
    pytest.param(
        "memory:///so-tests/file.txt",
        {"skip_instance_cache": True},
        {"memory": {"skip_instance_cache": True}},
        id="memory-options",
    ),
    pytest.param(
        "simplecache::memory:///so-tests/file.txt",
        {},
        {},
        id="simplecache-memory",
    ),
    pytest.param(
        "simplecache::memory:///so-tests/file.txt",
        {"memory": {"skip_instance_cache": True}},
        {"memory": {"skip_instance_cache": True}},
        id="simplecache-memory-inner-options",
    ),
    pytest.param(
        "simplecache::memory:///so-tests/file.txt",
        {"same_names": True, "memory": {"skip_instance_cache": True}},
        {"simplecache": {"same_names": True}, "memory": {"skip_instance_cache": True}},
        id="simplecache-memory-options",
    ),
    pytest.param(
        "zip://file.txt::memory:///so-tests/archive.zip",
        {},
        {},
        id="zip-memory",
    ),
    pytest.param(
        "zip://file.txt::memory:///so-tests/archive.zip",
        {"allowZip64": True, "memory": {"skip_instance_cache": True}},
        {"zip": {"allowZip64": True}, "memory": {"skip_instance_cache": True}},
        id="zip-memory-options",
    ),
    pytest.param(
        "simplecache::zip://file.txt::memory:///so-tests/archive.zip",
        {"same_names": True, "memory": {"skip_instance_cache": True}},
        {"simplecache": {"same_names": True}, "memory": {"skip_instance_cache": True}},
        id="simplecache-zip-memory-options",
    ),
    pytest.param(
        "zip://file.txt::{local_zip}",
        {"file": {"auto_mkdir": False}},
        {"file": {"auto_mkdir": False}},
        id="zip-file-options",
    ),
    pytest.param(
        "{local_zip}",
        {"auto_mkdir": False},
        {"file": {"auto_mkdir": False}},
        id="file-options",
    ),
]


@pytest.mark.parametrize("urlpath,storage_options,expected", UNCHAINED_CASES)
def test_to_unchained(memory_files, local_zip, urlpath, storage_options, expected):
    urlpath = urlpath.format(local_zip=local_zip.as_uri())
    p = UPath(urlpath, **storage_options)
    assert p.storage_options.to_unchained() == expected


@pytest.mark.parametrize("urlpath,storage_options,expected", UNCHAINED_CASES)
def test_to_unchained_with_fsspec(
    memory_files, local_zip, urlpath, storage_options, expected
):
    urlpath = urlpath.format(local_zip=local_zip.as_uri())
    p = UPath(urlpath, **storage_options)
    unchained = p.storage_options.to_unchained()

    fs, path = url_to_fs(str(p), **unchained)
    assert type(fs) is type(p.fs)
    assert fs == p.fs  # same fsspec token
    assert path == p.path

    with fsspec.open(str(p), mode="rb", **unchained) as f:
        assert f.read() == p.read_bytes()


_xfail_outermost_protocol_key = pytest.mark.xfail(
    reason="UPath does not yet merge options under the outermost protocol key (#567)",
    strict=False,
)


@pytest.mark.parametrize(
    "urlpath,storage_options,expected",
    [
        pytest.param(
            *case.values,
            id=case.id,
            marks=(
                [_xfail_outermost_protocol_key]
                if case.id
                in {
                    "memory-options",
                    "simplecache-memory-options",
                    "zip-memory-options",
                    "simplecache-zip-memory-options",
                    "file-options",
                }
                else []
            ),
        )
        for case in UNCHAINED_CASES
    ],
)
def test_to_unchained_upath_roundtrip(
    memory_files, local_zip, urlpath, storage_options, expected
):
    urlpath = urlpath.format(local_zip=local_zip.as_uri())
    p = UPath(urlpath, **storage_options)
    unchained = p.storage_options.to_unchained()
    p2 = UPath(str(p), **unchained)
    assert p2 == p
    assert p2.storage_options.to_unchained() == unchained


def test_to_unchained_local_path_without_protocol():
    so = StorageOptions({"auto_mkdir": True}, protocol="")
    assert so.to_unchained() == {"file": {"auto_mkdir": True}}


def test_to_unchained_returns_copies():
    so = StorageOptions(
        {"target_protocol": "memory", "target_options": {"a": 1}},
        protocol="simplecache",
    )
    unchained = so.to_unchained()
    unchained["memory"]["a"] = 2
    assert so["target_options"] == {"a": 1}


def test_to_unchained_repeated_protocol_without_options():
    so = StorageOptions(
        {
            "target_protocol": "zip",
            "target_options": {
                "target_protocol": "memory",
                "fo": "/outer.zip",  # codespell:ignore fo
            },
            "fo": "inner.zip",  # codespell:ignore fo
        },
        protocol="zip",
    )
    assert so.to_unchained() == {}


def test_to_unchained_repeated_protocol_with_options():
    so = StorageOptions(
        {
            "allowZip64": True,
            "target_protocol": "zip",
            "target_options": {
                "target_protocol": "memory",
                "fo": "/outer.zip",  # codespell:ignore fo
            },
            "fo": "inner.zip",  # codespell:ignore fo
        },
        protocol="zip",
    )
    with pytest.raises(ValueError, match="'zip' appears multiple times"):
        so.to_unchained()
