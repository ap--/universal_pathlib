from __future__ import annotations

import sys
import warnings
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from itertools import chain
from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlencode
from urllib.parse import urlsplit

from fsspec.asyn import sync

from upath import UnsupportedOperation
from upath._stat import UPathStatResult
from upath.core import UPath
from upath.types import JoinablePathLike
from upath.types import QueryLike
from upath.types import StatResultType

if TYPE_CHECKING:
    from typing import Literal

    if sys.version_info >= (3, 11):
        from typing import Self
        from typing import Unpack
    else:
        from typing_extensions import Self
        from typing_extensions import Unpack

    from upath._chain import FSSpecChainParser
    from upath.types.storage_options import HTTPStorageOptions

__all__ = ["HTTPPath"]

# characters allowed unescaped in a uri fragment (RFC 3986 section 3.5)
_FRAGMENT_SAFE = "/?:@!$&'()*+,;="


def _encode_query(query: QueryLike, params: Mapping[str, str | int | float]) -> str:
    if query is not None and params:
        raise ValueError("provide either a query or keyword arguments, not both")
    if isinstance(query, str):
        if "#" in query:
            raise ValueError(f"invalid query string: {query!r}")
        return query.removeprefix("?")
    items: Iterable[tuple[str, str | int | float]]
    if params:
        items = params.items()
    elif isinstance(query, Mapping):
        items = query.items()
    else:
        items = query or ()
    pairs = []
    for key, value in items:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise TypeError(
                f"query values must be str, int or float, got {type(value).__name__}"
            )
        pairs.append((key, str(value)))
    return urlencode(pairs)


def _drop_query_fragment(arg: JoinablePathLike) -> JoinablePathLike:
    if isinstance(arg, HTTPPath):
        return arg._replace_url(query="", fragment="")
    elif isinstance(arg, str) and ("?" in arg or "#" in arg):
        return urlsplit(arg)._replace(query="", fragment="").geturl()
    else:
        return arg


class HTTPPath(UPath):
    __slots__ = ()

    if TYPE_CHECKING:

        def __init__(
            self,
            *args: JoinablePathLike,
            protocol: Literal["http", "https"] | None = ...,
            chain_parser: FSSpecChainParser = ...,
            **storage_options: Unpack[HTTPStorageOptions],
        ) -> None: ...

    @classmethod
    def _transform_init_args(
        cls,
        args: tuple[JoinablePathLike, ...],
        protocol: str,
        storage_options: dict[str, Any],
    ) -> tuple[tuple[JoinablePathLike, ...], str, dict[str, Any]]:
        # allow initialization via a path argument and protocol keyword
        if args and not str(args[0]).startswith(protocol):
            args = (f"{protocol}://{str(args[0]).lstrip('/')}", *args[1:])
        # query and fragment only apply to the last path segment
        if len(args) > 1:
            args = (*map(_drop_query_fragment, args[:-1]), args[-1])
        return args, protocol, storage_options

    def __str__(self) -> str:
        sr = urlsplit(super().__str__())
        return sr._replace(path=sr.path or "/").geturl()

    @property
    def path(self) -> str:
        sr = urlsplit(super().path)
        return sr._replace(path=sr.path or "/").geturl()

    def _replace_url(self, **components: str) -> Self:
        url = str(self)
        new_url = urlsplit(url)._replace(**components).geturl()
        if new_url == url:
            return self
        return self.with_segments(new_url)

    @property
    def query(self) -> Mapping[str, str]:
        params: dict[str, str] = {}
        for key, value in parse_qsl(urlsplit(str(self)).query, keep_blank_values=True):
            params.setdefault(key, value)
        return MappingProxyType(params)

    @property
    def fragment(self) -> str:
        return unquote(urlsplit(str(self)).fragment)

    def with_query(
        self,
        query: QueryLike = None,
        /,
        **params: str | int | float,
    ) -> Self:
        return self._replace_url(query=_encode_query(query, params))

    def with_fragment(self, fragment: str | None) -> Self:
        return self._replace_url(fragment=quote(fragment or "", safe=_FRAGMENT_SAFE))

    @property
    def name(self) -> str:
        return super(HTTPPath, self._replace_url(query="", fragment="")).name

    @property
    def parts(self) -> Sequence[str]:
        return super(HTTPPath, self._replace_url(query="", fragment="")).parts

    def stat(self, follow_symlinks: bool = True) -> StatResultType:
        if not follow_symlinks:
            warnings.warn(
                f"{type(self).__name__}.stat(follow_symlinks=False):"
                " is currently ignored.",
                UserWarning,
                stacklevel=2,
            )
        info = self.fs.info(self.path)
        if "url" in info:
            info["type"] = "directory" if info["url"].endswith("/") else "file"
        return UPathStatResult.from_info(info)

    def iterdir(self) -> Iterator[Self]:
        it = iter(super().iterdir())
        try:
            item0 = next(it)
        except (StopIteration, NotADirectoryError):
            raise NotADirectoryError(str(self))
        except FileNotFoundError:
            raise FileNotFoundError(str(self))
        else:
            yield from chain([item0], it)

    def resolve(
        self,
        strict: bool = False,
        follow_redirects: bool = True,
    ) -> Self:
        """Normalize the path and resolve redirects."""
        # special handling of trailing slash behaviour
        parts = list(self.parts)
        if parts[-1:] == ["."]:
            parts[-1:] = [""]
        if parts[-2:] == ["", ".."]:
            parts[-2:] = [""]
        pth = self.with_segments(*parts)
        sr = urlsplit(str(self))
        resolved_path = (
            super(HTTPPath, pth)
            .resolve(strict=strict)
            ._replace_url(query=sr.query, fragment=sr.fragment)
        )

        if follow_redirects:
            cls = type(self)
            # Get the fsspec fs
            fs = self.fs
            url = str(self)
            # Ensure we have a session
            session = sync(fs.loop, fs.set_session)
            # Use HEAD requests if the server allows it, falling back to GETs
            for method in (session.head, session.get):
                r = sync(fs.loop, method, url, allow_redirects=True)
                try:
                    r.raise_for_status()
                except Exception as exc:
                    if method == session.get:
                        raise FileNotFoundError(self) from exc
                else:
                    resolved_path = cls(str(r.url))
                    break

        return resolved_path

    def touch(self, mode: int = 0o666, exist_ok: bool = True) -> None:
        raise UnsupportedOperation

    def mkdir(
        self,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        raise UnsupportedOperation

    def unlink(self, missing_ok: bool = False) -> None:
        raise UnsupportedOperation

    def write_bytes(self, data: bytes) -> int:
        raise UnsupportedOperation("DataPath does not support writing")

    def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        raise UnsupportedOperation("DataPath does not support writing")
