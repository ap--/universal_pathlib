"""conversion of fsspec storage options to object_store configuration

The object_store crate (used by polars, obstore, delta-rs, and other rust
based tools) is configured via string key value pairs. See:

- https://docs.rs/object_store/latest/object_store/aws/enum.AmazonS3ConfigKey.html
- https://docs.rs/object_store/latest/object_store/gcp/enum.GoogleConfigKey.html
- https://docs.rs/object_store/latest/object_store/azure/enum.AzureConfigKey.html
- https://docs.rs/object_store/latest/object_store/enum.ClientConfigKey.html

"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from collections.abc import Mapping
from typing import Any

__all__ = [
    "OBJECT_STORE_PROTOCOLS",
    "to_object_store_config",
]

# options only affecting fsspec's own caching, async, or instance behavior
_FSSPEC_OPTIONS = frozenset(
    {
        "use_listings_cache",
        "listings_expiry_time",
        "max_paths",
        "skip_instance_cache",
        "asynchronous",
        "loop",
        "batch_size",
    }
)


class _ConfigBuilder:
    """collects object_store config and tracks unsupported options"""

    def __init__(self) -> None:
        self.config: dict[str, str] = {}
        self.unsupported: list[str] = []
        self._sources: dict[str, str] = {}

    def set(self, key: str, value: str, source: str) -> None:
        if key in self.config and self.config[key] != value:
            raise ValueError(
                f"storage options {self._sources[key]!r} and {source!r} set"
                f" conflicting values for object_store config key {key!r}"
            )
        self.config[key] = value
        self._sources.setdefault(key, source)

    def set_str(self, key: str, value: Any, source: str) -> None:
        if isinstance(value, str):
            self.set(key, value, source)
        else:
            self.unsupported.append(source)

    def set_bool(self, key: str, value: Any, source: str) -> None:
        self.set(key, "true" if value else "false", source)

    def set_endpoint(self, key: str, value: Any, source: str) -> None:
        self.set_str(key, value, source)
        if isinstance(value, str) and value.startswith("http://"):
            self.set("allow_http", "true", source)


# --- AWS S3 (s3fs) ---------------------------------------------------

_S3_STR_OPTIONS = {
    "key": "aws_access_key_id",
    "username": "aws_access_key_id",
    "secret": "aws_secret_access_key",
    "password": "aws_secret_access_key",
    "token": "aws_session_token",
}
_S3_BOOL_OPTIONS = {
    "anon": "aws_skip_signature",
    "requester_pays": "aws_request_payer",
}
_S3_CLIENT_KWARGS = {
    "region_name": "aws_region",
    "aws_access_key_id": "aws_access_key_id",
    "aws_secret_access_key": "aws_secret_access_key",
    "aws_session_token": "aws_session_token",
}
_S3_IGNORED_OPTIONS = frozenset(
    {
        "default_block_size",
        "default_fill_cache",
        "default_cache_type",
        "cache_regions",
        "max_concurrency",
        "fixed_upload_size",
        "version_aware",
    }
)


def _convert_s3(options: Mapping[str, Any], builder: _ConfigBuilder) -> None:
    for name, value in options.items():
        if value is None or name in _FSSPEC_OPTIONS or name in _S3_IGNORED_OPTIONS:
            continue
        elif name in _S3_STR_OPTIONS:
            builder.set_str(_S3_STR_OPTIONS[name], value, name)
        elif name in _S3_BOOL_OPTIONS:
            builder.set_bool(_S3_BOOL_OPTIONS[name], value, name)
        elif name == "endpoint_url":
            builder.set_endpoint("aws_endpoint", value, name)
        elif name == "client_kwargs" and isinstance(value, Mapping):
            for ck_name, ck_value in value.items():
                source = f"client_kwargs.{ck_name}"
                if ck_value is None:
                    continue
                elif ck_name in _S3_CLIENT_KWARGS:
                    builder.set_str(_S3_CLIENT_KWARGS[ck_name], ck_value, source)
                elif ck_name == "endpoint_url":
                    builder.set_endpoint("aws_endpoint", ck_value, source)
                else:
                    builder.unsupported.append(source)
        else:
            builder.unsupported.append(name)


# --- Google Cloud Storage (gcsfs) ------------------------------------

_GCS_IGNORED_OPTIONS = frozenset(
    {
        "project",
        "block_size",
        "consistency",
        "cache_timeout",
        "check_connection",
        "default_location",
        "version_aware",
    }
)


def _convert_gcs_token(value: Any, builder: _ConfigBuilder) -> None:
    # mirrors the token interpretation in gcsfs.credentials.GoogleCredentials
    if isinstance(value, str):
        if value == "google_default":
            pass  # object_store uses application default credentials by default
        elif value == "anon":
            builder.set_bool("google_skip_signature", True, "token")
        elif value in {"cache", "cloud", "browser"}:
            builder.unsupported.append("token")
        elif os.path.exists(value):
            # service account or authorized user credentials file
            builder.set("google_application_credentials", value, "token")
        else:
            # gcsfs treats non-file strings as raw access tokens
            builder.set("google_bearer_token", value, "token")
    elif isinstance(value, Mapping) and value.get("type") == "service_account":
        builder.set("google_service_account_key", json.dumps(dict(value)), "token")
    else:
        builder.unsupported.append("token")


def _convert_gcs(options: Mapping[str, Any], builder: _ConfigBuilder) -> None:
    for name, value in options.items():
        if value is None or name in _FSSPEC_OPTIONS or name in _GCS_IGNORED_OPTIONS:
            continue
        elif name == "token":
            _convert_gcs_token(value, builder)
        elif name == "endpoint_url":
            builder.set_endpoint("google_base_url", value, name)
        else:
            builder.unsupported.append(name)


# --- Azure Blob Storage / Data Lake Gen2 (adlfs) ---------------------

_AZURE_STR_OPTIONS = {
    "account_name": "azure_storage_account_name",
    "account_key": "azure_storage_account_key",
    "sas_token": "azure_storage_sas_key",
    "client_id": "azure_storage_client_id",
    "client_secret": "azure_storage_client_secret",
    "tenant_id": "azure_storage_tenant_id",
}
_AZURE_CONNECTION_STRING_OPTIONS = {
    "ACCOUNTNAME": "azure_storage_account_name",
    "ACCOUNTKEY": "azure_storage_account_key",
    "SHAREDACCESSSIGNATURE": "azure_storage_sas_key",
}
_AZURE_CONNECTION_STRING_IGNORED = frozenset(
    {"QUEUEENDPOINT", "TABLEENDPOINT", "FILEENDPOINT"}
)
_AZURE_IGNORED_OPTIONS = frozenset(
    {
        "blocksize",
        "default_fill_cache",
        "default_cache_type",
        "max_concurrency",
        "version_aware",
        "assume_container_exists",
    }
)


def _convert_azure_connection_string(
    connection_string: Any,
    builder: _ConfigBuilder,
) -> None:
    if not isinstance(connection_string, str):
        builder.unsupported.append("connection_string")
        return
    settings: dict[str, str] = {}
    for item in connection_string.split(";"):
        if not item.strip():
            continue
        name, sep, value = item.partition("=")
        if not sep:
            builder.unsupported.append("connection_string")
            return
        settings[name.strip().upper()] = value.strip()

    for name, value in settings.items():
        source = f"connection_string[{name}]"
        if name in _AZURE_CONNECTION_STRING_OPTIONS:
            builder.set(_AZURE_CONNECTION_STRING_OPTIONS[name], value, source)
        elif name == "BLOBENDPOINT":
            builder.set_endpoint("azure_storage_endpoint", value, source)
        elif name == "USEDEVELOPMENTSTORAGE":
            builder.set_bool(
                "azure_storage_use_emulator", value.lower() == "true", source
            )
        elif (
            name in {"DEFAULTENDPOINTSPROTOCOL", "ENDPOINTSUFFIX"}
            or name in _AZURE_CONNECTION_STRING_IGNORED
        ):
            continue
        else:
            builder.unsupported.append(source)

    account_name = settings.get("ACCOUNTNAME")
    if (
        "BLOBENDPOINT" not in settings
        and account_name
        and ("DEFAULTENDPOINTSPROTOCOL" in settings or "ENDPOINTSUFFIX" in settings)
    ):
        scheme = settings.get("DEFAULTENDPOINTSPROTOCOL", "https")
        suffix = settings.get("ENDPOINTSUFFIX", "core.windows.net")
        builder.set_endpoint(
            "azure_storage_endpoint",
            f"{scheme}://{account_name}.blob.{suffix}",
            "connection_string[ENDPOINTSUFFIX]",
        )


def _convert_azure(options: Mapping[str, Any], builder: _ConfigBuilder) -> None:
    for name, value in options.items():
        if value is None or name in _FSSPEC_OPTIONS or name in _AZURE_IGNORED_OPTIONS:
            continue
        elif name in _AZURE_STR_OPTIONS:
            builder.set_str(_AZURE_STR_OPTIONS[name], value, name)
        elif name == "anon":
            builder.set_bool("azure_skip_signature", value, name)
        elif name == "account_host":
            if isinstance(value, str):
                builder.set("azure_storage_endpoint", f"https://{value}", name)
            else:
                builder.unsupported.append(name)
        elif name == "connection_string":
            _convert_azure_connection_string(value, builder)
        else:
            builder.unsupported.append(name)


# --- local filesystem ------------------------------------------------


def _convert_local(options: Mapping[str, Any], builder: _ConfigBuilder) -> None:
    for name, value in options.items():
        if value is None or name in _FSSPEC_OPTIONS or name == "auto_mkdir":
            continue
        builder.unsupported.append(name)


_CONVERTERS: dict[str, Callable[[Mapping[str, Any], _ConfigBuilder], None]] = {
    "s3": _convert_s3,
    "s3a": _convert_s3,
    "gs": _convert_gcs,
    "gcs": _convert_gcs,
    "az": _convert_azure,
    "abfs": _convert_azure,
    "abfss": _convert_azure,
    "": _convert_local,
    "file": _convert_local,
    "local": _convert_local,
}

OBJECT_STORE_PROTOCOLS = frozenset(_CONVERTERS)


def to_object_store_config(
    protocol: str,
    storage_options: Mapping[str, Any],
) -> tuple[dict[str, str], list[str]]:
    """convert fsspec storage options to object_store config

    Returns the object_store config and a list of the storage options
    that could not be converted.
    """
    try:
        converter = _CONVERTERS[protocol]
    except KeyError:
        supported = ", ".join(repr(p) for p in sorted(OBJECT_STORE_PROTOCOLS) if p)
        raise ValueError(
            f"cannot convert storage options for protocol {protocol!r} to an"
            f" object_store config. Supported protocols: {supported}"
        ) from None
    builder = _ConfigBuilder()
    converter(storage_options, builder)
    return builder.config, builder.unsupported
