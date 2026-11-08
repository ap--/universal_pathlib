import copy
import io
import json
import pickle
import warnings
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


# === to_object_store =================================================


@pytest.mark.parametrize(
    "urlpath,storage_options,expected",
    [
        # --- s3fs ---
        ("s3://bucket/key", {}, {}),
        ("s3://bucket/key", {"anon": True}, {"aws_skip_signature": "true"}),
        ("s3://bucket/key", {"anon": False}, {"aws_skip_signature": "false"}),
        (
            "s3://bucket/key",
            {"key": "AKID", "secret": "SECRET", "token": "TOKEN"},
            {
                "aws_access_key_id": "AKID",
                "aws_secret_access_key": "SECRET",
                "aws_session_token": "TOKEN",
            },
        ),
        (
            "s3a://bucket/key",
            {"username": "AKID", "password": "SECRET"},
            {"aws_access_key_id": "AKID", "aws_secret_access_key": "SECRET"},
        ),
        (
            "s3://bucket/key",
            {"endpoint_url": "https://s3.example.com"},
            {"aws_endpoint": "https://s3.example.com"},
        ),
        (
            "s3://bucket/key",
            {"endpoint_url": "http://localhost:9000"},
            {"aws_endpoint": "http://localhost:9000", "allow_http": "true"},
        ),
        (
            "s3://bucket/key",
            {
                "client_kwargs": {
                    "endpoint_url": "http://localhost:9000",
                    "region_name": "eu-central-1",
                },
            },
            {
                "aws_endpoint": "http://localhost:9000",
                "allow_http": "true",
                "aws_region": "eu-central-1",
            },
        ),
        (
            "s3://bucket/key",
            {
                "client_kwargs": {
                    "aws_access_key_id": "AKID",
                    "aws_secret_access_key": "SECRET",
                    "aws_session_token": "TOKEN",
                },
            },
            {
                "aws_access_key_id": "AKID",
                "aws_secret_access_key": "SECRET",
                "aws_session_token": "TOKEN",
            },
        ),
        (
            "s3://bucket/key",
            {"key": "AKID", "client_kwargs": {"aws_access_key_id": "AKID"}},
            {"aws_access_key_id": "AKID"},
        ),
        ("s3://bucket/key", {"requester_pays": True}, {"aws_request_payer": "true"}),
        (
            "s3://bucket/key",
            {
                "use_listings_cache": False,
                "skip_instance_cache": True,
                "default_block_size": 1024,
                "default_cache_type": "none",
                "version_aware": True,
                "key": None,
            },
            {},
        ),
        # --- gcsfs ---
        ("gs://bucket/key", {}, {}),
        ("gs://bucket/key", {"token": "anon"}, {"google_skip_signature": "true"}),
        ("gcs://bucket/key", {"token": "google_default", "project": "p"}, {}),
        ("gs://bucket/key", {"token": None}, {}),
        (
            "gs://bucket/key",
            {"token": "ya29.access-token"},
            {"google_bearer_token": "ya29.access-token"},
        ),
        (
            "gs://bucket/key",
            {"endpoint_url": "http://localhost:4443"},
            {"google_base_url": "http://localhost:4443", "allow_http": "true"},
        ),
        # --- adlfs ---
        ("az://container/key", {}, {}),
        (
            "az://container/key",
            {"account_name": "acct", "account_key": "KEY"},
            {
                "azure_storage_account_name": "acct",
                "azure_storage_account_key": "KEY",
            },
        ),
        (
            "abfss://container@acct.dfs.core.windows.net/key",
            {"sas_token": "?sv=2020&sig=abc"},
            {
                "azure_storage_account_name": "acct",
                "azure_storage_sas_key": "?sv=2020&sig=abc",
            },
        ),
        (
            "abfs://container/key",
            {
                "account_name": "acct",
                "tenant_id": "tenant",
                "client_id": "client",
                "client_secret": "secret",
            },
            {
                "azure_storage_account_name": "acct",
                "azure_storage_tenant_id": "tenant",
                "azure_storage_client_id": "client",
                "azure_storage_client_secret": "secret",
            },
        ),
        (
            "az://container/key",
            {"account_name": "acct", "anon": True},
            {"azure_storage_account_name": "acct", "azure_skip_signature": "true"},
        ),
        (
            "az://container/key",
            {"account_name": "acct", "account_host": "acct.blob.example.com"},
            {
                "azure_storage_account_name": "acct",
                "azure_storage_endpoint": "https://acct.blob.example.com",
            },
        ),
        (
            "az://container/key",
            {
                "connection_string": (
                    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
                    "AccountKey=a2V5==;"
                    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
                    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
                ),
            },
            {
                "azure_storage_account_name": "devstoreaccount1",
                "azure_storage_account_key": "a2V5==",
                "azure_storage_endpoint": "http://127.0.0.1:10000/devstoreaccount1",
                "allow_http": "true",
            },
        ),
        (
            "az://container/key",
            {
                "connection_string": (
                    "DefaultEndpointsProtocol=https;AccountName=acct;"
                    "SharedAccessSignature=sv=2020&sig=abc;"
                    "EndpointSuffix=core.chinacloudapi.cn"
                ),
            },
            {
                "azure_storage_account_name": "acct",
                "azure_storage_sas_key": "sv=2020&sig=abc",
                "azure_storage_endpoint": "https://acct.blob.core.chinacloudapi.cn",
            },
        ),
        (
            "az://container/key",
            {"connection_string": "UseDevelopmentStorage=true"},
            {"azure_storage_use_emulator": "true"},
        ),
        # --- local ---
        ("file:///tmp/file.txt", {"auto_mkdir": True}, {}),
    ],
)
def test_to_object_store(urlpath, storage_options, expected):
    p = UPath(urlpath, **storage_options)
    config = p.storage_options.to_object_store()
    assert config == expected
    assert all(isinstance(v, str) for v in config.values())


def test_to_object_store_local_path(tmp_path):
    assert UPath(tmp_path).storage_options.to_object_store() == {}


def test_to_object_store_gcs_token_file(tmp_path):
    token_file = tmp_path.joinpath("credentials.json")
    token_file.write_text('{"type": "authorized_user"}')
    p = UPath("gs://bucket/key", token=str(token_file))
    assert p.storage_options.to_object_store() == {
        "google_application_credentials": str(token_file),
    }


def test_to_object_store_gcs_service_account_info():
    info = {
        "type": "service_account",
        "client_email": "name@project.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\n...",
    }
    p = UPath("gs://bucket/key", token=info)
    config = p.storage_options.to_object_store()
    assert list(config) == ["google_service_account_key"]
    assert json.loads(config["google_service_account_key"]) == info


@pytest.mark.parametrize(
    "urlpath",
    [
        "memory:///a/b",
        "simplecache::s3://bucket/key",
        "zip://file.txt::s3://bucket/archive.zip",
        "https://example.com/file.txt",
    ],
)
def test_to_object_store_unsupported_protocol(urlpath):
    so = UPath(urlpath).storage_options
    with pytest.raises(ValueError, match=f"protocol {so.protocol!r}"):
        so.to_object_store()


@pytest.mark.parametrize(
    "urlpath,storage_options,unsupported",
    [
        ("s3://bucket/key", {"profile": "default"}, "'profile'"),
        (
            "s3://bucket/key",
            {"client_kwargs": {"verify": False}},
            "'client_kwargs.verify'",
        ),
        ("s3://bucket/key", {"config_kwargs": {"retries": {}}}, "'config_kwargs'"),
        ("s3://bucket/key", {"key": 1234}, "'key'"),
        ("gs://bucket/key", {"token": "cloud"}, "'token'"),
        ("gs://bucket/key", {"token": object()}, "'token'"),
        ("gs://bucket/key", {"token": {"refresh_token": "x"}}, "'token'"),
        ("gs://bucket/key", {"requester_pays": True}, "'requester_pays'"),
        ("az://container/key", {"credential": "xyz"}, "'credential'"),
        (
            "az://container/key",
            {"connection_string": "AccountName=a;Unknown=b"},
            "'connection_string\\[UNKNOWN\\]'",
        ),
        ("file:///tmp/file.txt", {"something": 1}, "'something'"),
    ],
)
def test_to_object_store_unsupported_options(urlpath, storage_options, unsupported):
    so = UPath(urlpath, **storage_options).storage_options
    with pytest.raises(ValueError, match=unsupported):
        so.to_object_store()


def test_to_object_store_non_strict():
    p = UPath(
        "s3://bucket/key",
        anon=True,
        profile="default",
        client_kwargs={"verify": False, "region_name": "us-east-1"},
    )
    with pytest.warns(UserWarning, match="'profile', 'client_kwargs.verify'") as w:
        config = p.storage_options.to_object_store(strict=False)
    assert w[0].filename == __file__
    assert config == {"aws_skip_signature": "true", "aws_region": "us-east-1"}


def test_to_object_store_strict_does_not_warn():
    p = UPath("s3://bucket/key", anon=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert p.storage_options.to_object_store(strict=False) == {
            "aws_skip_signature": "true"
        }


@pytest.mark.parametrize(
    "urlpath,storage_options",
    [
        ("s3://bucket/key", {"key": "A", "client_kwargs": {"aws_access_key_id": "B"}}),
        (
            "s3://bucket/key",
            {
                "endpoint_url": "https://a.example.com",
                "client_kwargs": {"endpoint_url": "https://b.example.com"},
            },
        ),
        (
            "az://container/key",
            {"account_name": "a", "connection_string": "AccountName=b"},
        ),
    ],
)
def test_to_object_store_conflicting_options(urlpath, storage_options):
    so = UPath(urlpath, **storage_options).storage_options
    with pytest.raises(ValueError, match="conflicting values") as e:
        so.to_object_store()
    # values are not part of the error message
    assert "'A'" not in str(e.value) and "'B'" not in str(e.value)
