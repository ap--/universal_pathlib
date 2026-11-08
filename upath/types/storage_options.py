"""Storage options types for various filesystems based on fsspec."""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from collections.abc import Mapping
from pprint import pformat
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from typing import Literal

    from fsspec.implementations.cache_mapper import AbstractCacheMapper
    from fsspec.spec import AbstractFileSystem


__all__ = [
    "StorageOptions",
    "SimpleCacheStorageOptions",
    "GCSStorageOptions",
    "S3StorageOptions",
    "AzureStorageOptions",
    "HfStorageOptions",
    "DataStorageOptions",
    "FTPStorageOptions",
    "GitHubStorageOptions",
    "HDFSStorageOptions",
    "HTTPStorageOptions",
    "FileStorageOptions",
    "MemoryStorageOptions",
    "SFTPStorageOptions",
    "SMBStorageOptions",
    "WebdavStorageOptions",
    "ZipStorageOptions",
    "TarStorageOptions",
]

_REDACTED = "***"
_SENSITIVE_KEY_PARTS = (
    "key",
    "secret",
    "token",
    "password",
    "passphrase",
    "credential",
    "auth",
    "sas",
    "connection_string",
)
# gcsfs token values that select an authentication method
_NON_SECRET_TOKENS = frozenset({"anon", "google_default", "cache", "cloud", "browser"})


def _is_sensitive(key: Any, value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return False
    elif not isinstance(key, str):
        return False
    elif key == "token" and isinstance(value, str) and value in _NON_SECRET_TOKENS:
        return False
    key = key.lower()
    return any(part in key for part in _SENSITIVE_KEY_PARTS)


def _redact(options: Mapping[str, Any]) -> dict[str, Any]:
    """return a copy of options with credential-like values redacted"""
    redacted: dict[str, Any] = {}
    for key, value in options.items():
        if _is_sensitive(key, value):
            value = _REDACTED
        elif isinstance(value, Mapping):
            value = _redact(value)
        redacted[key] = value
    return redacted


def _make_storage_options(
    cls: type[StorageOptions],
    options: Mapping[str, Any],
    protocol: str,
) -> StorageOptions:
    """helper for pickling StorageOptions instances"""
    return cls(options, protocol=protocol)


class StorageOptions(Mapping[str, Any]):
    """Read-only mapping of the fsspec storage options of a path.

    `UPath.storage_options` returns an instance of this class. It behaves
    like a read-only `dict` (it compares equal to plain dicts and can be
    unpacked via `**`), and it knows the `protocol` of the filesystem the
    options belong to, which allows converting the options to formats
    understood by other libraries.

    For chained paths (e.g. `"simplecache::s3://bucket/file.txt"`), the
    storage options of the inner filesystems are nested under the
    `target_protocol` / `target_options` keys, exactly like they are
    passed to the outermost fsspec filesystem.

    Parameters
    ----------
    options :
        The fsspec storage options.
    protocol :
        The fsspec protocol of the filesystem the options belong to.

    Note
    ----
    The `repr` of a `StorageOptions` instance redacts values of keys that
    look like credentials (e.g. `secret`, `token`, `account_key`, ...).
    Use `dict(storage_options)` to access the actual values.

    Examples
    --------
    >>> from upath import UPath
    >>> p = UPath("s3://bucket/file.txt", anon=True)
    >>> p.storage_options
    StorageOptions({'anon': True}, protocol='s3')
    >>> p.storage_options == {"anon": True}
    True

    """

    __slots__ = ("_options", "_protocol")

    def __init__(
        self,
        options: Mapping[str, Any] | None = None,
        /,
        *,
        protocol: str,
    ) -> None:
        self._options: dict[str, Any] = dict(options) if options is not None else {}
        self._protocol = protocol

    @property
    def protocol(self) -> str:
        """The fsspec protocol of the filesystem the options belong to."""
        return self._protocol

    # === Mapping interface ===========================================

    def __getitem__(self, key: str) -> Any:
        return self._options[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._options)

    def __len__(self) -> int:
        return len(self._options)

    def __contains__(self, key: object) -> bool:
        return key in self._options

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StorageOptions):
            return self._options == other._options
        elif isinstance(other, Mapping):
            return self._options == dict(other.items())
        else:
            return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    # === types.MappingProxyType compatibility ========================

    def copy(self) -> dict[str, Any]:
        """Return a shallow copy of the storage options as a `dict`."""
        return self._options.copy()

    def __reversed__(self) -> Iterator[str]:
        return reversed(self._options)

    def __or__(self, other: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(other, Mapping):
            return NotImplemented
        return {**self._options, **other}

    def __ror__(self, other: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(other, Mapping):
            return NotImplemented
        return {**other, **self._options}

    def __reduce__(self) -> tuple[Any, ...]:
        return _make_storage_options, (type(self), self._options, self._protocol)

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        options = _redact(self._options)
        text = f"{cls_name}({options!r}, protocol={self._protocol!r})"
        if len(text) <= 80:
            return text
        formatted = textwrap.indent(
            pformat(options, width=76, sort_dicts=False), "    "
        )
        return f"{cls_name}(\n{formatted},\n    protocol={self._protocol!r},\n)"

    # === conversions =================================================

    def to_unchained(self) -> dict[str, dict[str, Any]]:
        """Return the storage options keyed by protocol.

        This is the format `fsspec.open` and `fsspec.core.url_to_fs` use
        for chained urlpaths: the options of every filesystem in the chain
        are provided under the corresponding protocol key. The nested
        `target_protocol`, `target_options` and `fo` keys of chained
        filesystems are resolved. Filesystems without storage options are
        omitted. Local paths without protocol are keyed under `"file"`.

        Raises
        ------
        ValueError
            If the same protocol appears more than once in the chain and
            the options can't be unambiguously assigned to a protocol key.

        Examples
        --------
        >>> import fsspec
        >>> from upath import UPath
        >>> p = UPath(
        ...     "simplecache::memory:///file.txt",
        ...     cache_storage="/tmp/cache",
        ...     memory={"skip_instance_cache": True},
        ... )
        >>> p.storage_options.to_unchained()
        {'simplecache': {'cache_storage': '/tmp/cache'}, 'memory': {'skip_instance_cache': True}}
        >>> f = fsspec.open(str(p), **p.storage_options.to_unchained())

        """  # noqa: E501
        unchained: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        protocol = self._protocol
        options = dict(self._options)
        while True:
            is_chained = "target_protocol" in options
            if is_chained:
                target_protocol = options.pop("target_protocol")
                target_options = options.pop("target_options", None) or {}
                options.pop("fo", None)  # codespell:ignore fo
            key = protocol or "file"
            if key in seen and (options or key in unchained):
                raise ValueError(
                    f"cannot unchain storage options: protocol {key!r} appears"
                    " multiple times in the chain"
                )
            seen.add(key)
            if options:
                unchained[key] = options
            if not is_chained:
                return unchained
            protocol = target_protocol
            options = dict(target_options)


class _AbstractStorageOptions(TypedDict, total=False):
    """Base storage options for fsspec-based filesystems"""

    # dircache related options
    use_listings_cache: bool
    listings_expiry_time: int | float | None
    max_paths: int | None
    # fs instance cache options
    skip_instance_cache: bool
    # async fs instance options
    asynchronous: bool
    loop: AbstractEventLoop | None
    batch_size: int | None


class _ChainableStorageOptions(TypedDict, total=False):
    """Storage options for filesystems supporting chaining"""

    target_protocol: str | None
    target_options: dict[str, Any] | None
    fs: AbstractFileSystem | None


class SimpleCacheStorageOptions(
    _AbstractStorageOptions,
    _ChainableStorageOptions,
    total=False,
):
    """Storage options for SimpleCache"""

    cache_storage: Literal["TMP"] | list[str] | str
    cache_check: int | Literal[False]
    check_files: bool
    expiry_time: int | Literal[False]
    same_names: bool | None
    compression: str  # todo: specify allowed values
    cache_mapper: AbstractCacheMapper | None


class GCSStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for Google Cloud Storage"""

    # Authentication and project settings
    project: str
    access: Literal["read_only", "read_write", "full_control"]
    token: (
        None
        | Literal["google_default", "cache", "anon", "browser", "cloud"]
        | str
        | dict[str, Any]
    )

    # Performance and caching
    block_size: int | None
    consistency: Literal["none", "size", "md5"]
    cache_timeout: float | None  # overrides listings_expiry_time if set

    # Request configuration
    requests_timeout: float | None
    requester_pays: bool | str
    session_kwargs: dict[str, Any] | None  # aiohttp.ClientSession kwargs
    timeout: float | None  # timeout used for .buckets?

    # Connection settings
    endpoint_url: str | None
    check_connection: bool | None

    # Storage configuration
    default_location: str | None
    version_aware: bool

    # Deprecated options
    # secure_serialize: bool


class S3StorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for AWS S3 and S3-compatible services"""

    # Authentication
    anon: bool
    key: str | None
    secret: str | None
    token: str | None
    username: str | None  # alias for key
    password: str | None  # alias for secret

    # Connection settings
    endpoint_url: str | None
    use_ssl: bool

    # AWS-specific configuration
    client_kwargs: dict[str, Any] | None  # botocore Client kwargs
    config_kwargs: dict[str, Any] | None  # botocore Config kwargs
    s3_additional_kwargs: dict[str, Any] | None  # s3 api methods kwargs
    session: Any | None  # aiobotocore AioSession

    # Performance settings
    requester_pays: bool
    default_block_size: int | None
    default_fill_cache: bool
    default_cache_type: str  # fsspec.caching Literal["readahead", "none", "bytes", ...]
    max_concurrency: int
    fixed_upload_size: bool

    # Feature flags
    version_aware: bool
    cache_regions: bool


class AzureStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for Azure Blob Storage and Azure Data Lake Gen2"""

    # Account and authentication
    account_name: str | None
    account_key: str | None
    connection_string: str | None
    credential: (
        str | Any | None
    )  # azure.core.credentials_async.AsyncTokenCredential or SAS token
    sas_token: str | None
    anon: bool | None

    # Service Principal authentication
    client_id: str | None
    client_secret: str | None
    tenant_id: str | None

    # Connection and networking
    # request_session: Any | None  # for http requests not used by anything ???
    # socket_timeout: int | None  deprecated
    account_host: str | None
    location_mode: Literal["primary", "secondary"]

    # Performance settings
    blocksize: int  # block size for download/upload operations
    default_fill_cache: bool
    default_cache_type: str  # fsspec cache type
    max_concurrency: int | None

    # Timeout settings
    timeout: int | None  # server-side timeout for operations
    connection_timeout: int | None  # connection establishment timeout
    read_timeout: int | None  # read operation timeout

    # Feature flags
    version_aware: bool  # support blob versioning
    assume_container_exists: bool | None  # container existence assumptions


class HfStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for Hugging face filesystem"""

    # Authentication
    token: str | None

    # Connection settings
    endpoint: str | None

    # Performance settings
    block_size: (
        int | None
    )  # Block size for reading bytes; 0 = raw requests file-like objects


class DataStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for Data URIs filesystem"""

    # No specific options for Data URIs at the moment


class FTPStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for FTP filesystem"""

    # Connection settings
    host: str  # The remote server name/ip to connect to (required)
    port: int  # Port to connect with (default: 21)

    # Authentication
    username: (
        str | None
    )  # User's identifier for authentication (anonymous if not given)
    password: str | None  # User's password on the server
    acct: str | None  # Account string for authentication (some servers require this)

    # Performance settings
    block_size: int | None  # Read-ahead or write buffer size

    # FTP-specific settings
    tempdir: (
        str | None
    )  # Directory on remote to put temporary files when in a transaction
    timeout: int  # Timeout of the FTP connection in seconds (default: 30)
    encoding: str  # Encoding for dir and filenames in FTP connection (default: "utf-8")

    # Security settings
    tls: bool  # Use FTP-TLS (default: False)


class GitHubStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for GitHub repository filesystem"""

    # Repository identification
    org: str  # GitHub organization or username
    repo: str  # Repository name
    sha: str | None  # Commit SHA, branch, or tag (default: current master)

    # Authentication
    username: str | None  # GitHub username for authenticated access
    token: str | None  # GitHub personal access token

    # Connection settings
    timeout: tuple[int, int] | int | None  # (connect, read) timeouts or single timeout


class HDFSStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for Hadoop Distributed File System (HDFS)"""

    # Connection settings
    host: str  # Hostname, IP or "default" to try to read from Hadoop config
    port: int  # Port to connect on, or default from Hadoop config if 0

    # Authentication
    user: str | None  # Username to connect as
    kerb_ticket: str | None  # Kerberos ticket for authentication

    # HDFS-specific settings
    replication: int  # Replication factor for write operations (default: 3)
    extra_conf: (
        dict[str, Any] | None
    )  # Additional configuration passed to HadoopFileSystem


class HTTPStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for HTTP(S) filesystem"""

    # Performance settings
    block_size: (
        int | None
    )  # Block size for reading bytes; 0 = raw requests file-like objects

    # Link parsing behavior
    simple_links: (
        bool  # Consider both HTML <a> tags and URL-like strings vs HTML tags only
    )
    same_scheme: (
        bool  # Only consider paths with matching http/https scheme during ls/glob
    )

    # Caching configuration
    cache_type: str  # Default cache type used in open() (e.g., "bytes")
    cache_options: dict[str, Any] | None  # Default cache options used in open()

    # HTTP client configuration
    client_kwargs: dict[str, Any] | None  # Passed to aiohttp.ClientSession
    get_client: Any | None  # Callable that constructs aiohttp.ClientSession

    # Encoding settings
    encoded: bool  # Whether URLs should be encoded

    # Deprecated options
    # size_policy: Any  # Deprecated parameter


class FileStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for local filesystem (file:// and local:// protocols)"""

    # File system behavior
    auto_mkdir: bool  # Whether to create parent directories when opening files


class MemoryStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for memory filesystem"""

    # No specific options for memory filesystem at the moment


class SFTPStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for SFTP/SSH filesystem"""

    # Connection settings
    host: str  # Hostname or IP address (required)
    port: int | None  # SSH port (default: 22)

    # Authentication
    username: str | None  # Username to authenticate as
    password: (
        str | None
    )  # Password authentication; also used for private key decryption
    passphrase: str | None  # Used for decrypting private keys
    pkey: Any | None  # Private key for authentication (paramiko.PKey)
    key_filename: str | list[str] | None  # Filename(s) of private key(s)/certs to try

    # Connection behavior
    timeout: float | None  # TCP connect timeout in seconds
    allow_agent: bool | None  # Whether to connect to SSH agent (default: True)
    look_for_keys: (
        bool | None
    )  # Whether to search for private keys in ~/.ssh/ (default: True)
    compress: bool | None  # Whether to turn on compression
    sock: Any | None  # Socket or socket-like object for communication

    # GSS-API authentication
    gss_auth: bool | None  # Use GSS-API authentication
    gss_kex: bool | None  # Perform GSS-API Key Exchange and user authentication
    gss_deleg_creds: bool | None  # Delegate GSS-API client credentials
    gss_host: str | None  # Target name in kerberos database (default: hostname)
    gss_trust_dns: bool | None  # Trust DNS to canonicalize hostname (default: True)

    # Timeout settings
    banner_timeout: float | None  # SSH banner timeout in seconds
    auth_timeout: float | None  # Authentication response timeout in seconds
    channel_timeout: float | None  # Channel open response timeout in seconds

    # Advanced configuration
    disabled_algorithms: (
        dict[str, Any] | None
    )  # Algorithms to disable (passed to Transport)
    transport_factory: Any | None  # Callable to generate Transport instance
    auth_strategy: Any | None  # AuthStrategy instance for newer authentication

    # SFTP-specific settings
    temppath: str  # Remote temporary directory path (default: "/tmp")


class SMBStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for SMB/Windows/Samba network shares"""

    # Connection settings
    host: str  # The remote server name/ip to connect to (required)
    port: int | None  # Port to connect with (usually 445, sometimes 139)

    # Authentication
    username: str | None  # Username to connect with (required if not using Kerberos)
    password: str | None  # User's password on the server

    # Connection behavior
    timeout: int  # Connection timeout in seconds (default: 60)
    encrypt: bool | None  # Whether to force encryption

    # File access control
    share_access: Literal["r", "w", "d"] | None  # Default access for file operations
    # None (default): exclusively locks file until closed
    # 'r': Allow other handles with read access
    # 'w': Allow other handles with write access
    # 'd': Allow other handles with delete access

    # Session retry configuration
    register_session_retries: int  # Number of session registration retries (default: 4)
    register_session_retry_wait: (
        int  # Wait time between retries in seconds (default: 1)
    )
    register_session_retry_factor: int  # Exponential backoff factor (default: 10)

    # File system behavior
    auto_mkdir: bool  # Whether to create parent directories when opening files


class WebdavStorageOptions(_AbstractStorageOptions, total=False):
    """Storage options for WebDAV filesystem"""

    # Connection settings
    base_url: str  # Base URL of the WebDAV server (required)

    # Authentication
    auth: (
        tuple[str, str] | Any | None
    )  # Authentication (username, password) tuple or custom auth

    # Client configuration
    client: Any | None  # webdav4.client.Client instance


class ZipStorageOptions(
    _AbstractStorageOptions,
    _ChainableStorageOptions,
    total=False,
):
    """Storage options for ZIP archive filesystem"""

    # Archive file settings
    fo: str | Any  # Path to ZIP file or file-like object
    mode: Literal["r", "w", "a"]  # Open mode: read, write, or append

    # ZIP compression settings
    compression: int  # Compression method (e.g., zipfile.ZIP_STORED, ZIP_DEFLATED)
    allowZip64: bool  # Enable ZIP64 extensions for large files
    compresslevel: int | None  # Compression level (None uses default for method)


class TarStorageOptions(
    _AbstractStorageOptions,
    _ChainableStorageOptions,
    total=False,
):
    """Storage options for TAR archive filesystem (read-only)"""

    # Archive file settings
    fo: str | Any  # Path to TAR file or file-like object
    # Compression settings
    compression: (
        str | None
    )  # Compression method: 'gzip', 'bz2', 'xz', or None for auto-detect
    index_store: str | None  # Path to store/load the file index cache
