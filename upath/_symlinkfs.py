"""upath._symlinkfs: a chainable fsspec filesystem emulating symbolic links

This is an experimental prototype. Symlinks are stored in an in-memory
mapping `{link_path: target}` that is layered on top of a target
filesystem, which itself does not need to support symlinks:

>>> from upath import UPath
>>> p = UPath(
...     "symlinks::memory://data/latest",
...     symlinks={"mapping": {"/data/latest": "./v2"}},
... )

Semantics follow POSIX where possible:
- `link_path` keys are (protocol stripped) paths of the target filesystem
- targets starting with `/` or containing `://` are absolute paths of the
  target filesystem, all other targets are relative to the link's parent
- `info()` follows links (`islink`/`destination` keys like LocalFileSystem),
  `ls()` reports links with `type="other"` so `walk`/`find`/`rm` don't
  recurse into linked directories
- reading/writing follows links, `rm`/`mv` operate on the link itself
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Mapping
from typing import Any

from fsspec import AbstractFileSystem
from fsspec import filesystem

try:
    from fsspec.implementations.chained import ChainedFileSystem
except ImportError:  # fsspec < 2025.10.0
    ChainedFileSystem = AbstractFileSystem  # type: ignore[misc,assignment]

__all__ = ["SymlinkFileSystem"]

MAXSYMLINKS = 40


def _is_relative_target(target: str) -> bool:
    return not (target.startswith("/") or "://" in target)


class SymlinkFileSystem(ChainedFileSystem):
    """pass-through filesystem adding emulated symlinks to a target filesystem

    Parameters
    ----------
    target_protocol:
        protocol of the target filesystem
    target_options:
        storage options for the target filesystem
    fs:
        an already instantiated target filesystem (instead of protocol/options)
    mapping:
        initial `{link_path: target}` symlink mapping
    """

    protocol = "symlinks"

    def __init__(
        self,
        target_protocol: str | None = None,
        target_options: dict[str, Any] | None = None,
        fs: AbstractFileSystem | None = None,
        mapping: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("fo", None)  # provided by fsspec/upath url chaining
        super().__init__(**kwargs)
        if fs is None:
            if target_protocol is None:
                raise ValueError("provide either `fs` or `target_protocol`")
            fs = filesystem(target_protocol, **(target_options or {}))
        self.fs = fs
        self.mapping: dict[str, str] = {
            self._join(self._split(k)): v for k, v in (mapping or {}).items()
        }
        # store links under their canonical location (no links in parents)
        self.mapping = {self._link_key(k): v for k, v in self.mapping.items()}

    # --- path helpers ---

    def _split(self, path: str) -> list[str]:
        path = self.fs._strip_protocol(path)
        root = self.fs.root_marker
        if root and path.startswith(root):
            path = path[len(root) :]
        return [part for part in path.split("/") if part]

    def _join(self, parts: list[str]) -> str:
        return self.fs.root_marker + "/".join(parts)

    def _target_parts(self, target: str) -> tuple[bool, list[str]]:
        if _is_relative_target(target):
            return True, target.split("/")
        return False, self._split(target)

    def _resolve_parts(self, parts: list[str], follow_last: bool = True) -> list[str]:
        resolved: list[str] = []
        todo = parts[::-1]
        hops = 0
        while todo:
            part = todo.pop()
            if part in {"", "."}:
                continue
            elif part == "..":
                if resolved:
                    resolved.pop()
                continue
            target = self.mapping.get(self._join([*resolved, part]))
            if target is not None and (todo or follow_last):
                hops += 1
                if hops > MAXSYMLINKS:
                    raise OSError(
                        errno.ELOOP, os.strerror(errno.ELOOP), self._join(parts)
                    )
                relative, target_parts = self._target_parts(target)
                if not relative:
                    resolved = []
                todo.extend(target_parts[::-1])
            else:
                resolved.append(part)
        return resolved

    def _resolve(self, path: str, follow_last: bool = True) -> str:
        """return the target filesystem path with all symlinks resolved"""
        return self._join(self._resolve_parts(self._split(path), follow_last))

    def _link_key(self, path: str) -> str:
        """return the canonical location of path without following it"""
        parts = self._split(path)
        if not parts or parts[-1] in {".", ".."}:
            return self._resolve(path)
        return self._join([*self._resolve_parts(parts[:-1]), parts[-1]])

    def _is_implied_dir(self, real: str) -> bool:
        prefix = real.rstrip("/") + "/" if real.strip("/") else self.fs.root_marker
        return any(k.startswith(prefix) for k in self.mapping)

    def _real_info(self, real: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.fs.info(real, **kwargs)
        except FileNotFoundError:
            if self._is_implied_dir(real):
                return {"name": real, "type": "directory", "size": 0}
            raise

    # --- symlink api ---

    def islink(self, path: str) -> bool:
        return self._link_key(path) in self.mapping

    def lexists(self, path: str, **kwargs: Any) -> bool:
        return self.islink(path) or self.exists(path, **kwargs)

    def readlink(self, path: str) -> str:
        try:
            return self.mapping[self._link_key(path)]
        except KeyError:
            raise OSError(errno.EINVAL, os.strerror(errno.EINVAL), path) from None

    def symlink(self, src: str, dst: str, **kwargs: Any) -> None:
        """create a symlink at dst pointing to src (like os.symlink)"""
        if self.lexists(dst):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), dst)
        self.mapping[self._link_key(dst)] = src

    # --- AbstractFileSystem ---

    def info(
        self, path: str, follow_symlinks: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        name = self._join(self._split(path))
        key = self._link_key(path)
        if key not in self.mapping:
            return {**self._real_info(key, **kwargs), "name": name, "islink": False}
        destination = self.mapping[key]
        if not follow_symlinks:
            return {
                "name": name,
                "type": "other",
                "size": len(destination),
                "mode": stat.S_IFLNK | 0o777,
                "islink": True,
                "destination": destination,
            }
        out = self._real_info(self._resolve(path), **kwargs)
        return {**out, "name": name, "islink": True, "destination": destination}

    def ls(self, path: str, detail: bool = True, **kwargs: Any) -> list[Any]:
        parts = self._split(path)
        real_parts = self._resolve_parts(parts)
        real = self._join(real_parts)
        n = len(real_parts)
        links = {k for k in self.mapping if self._split(k)[:-1] == real_parts}
        implied = {
            k_parts[n]
            for k in self.mapping
            if len(k_parts := self._split(k)) > n + 1 and k_parts[:n] == real_parts
        }

        try:
            entries = self.fs.ls(real, detail=True, **kwargs)
        except FileNotFoundError:
            if not links and not implied:
                raise
            entries = []

        out: dict[str, dict[str, Any]] = {}
        for entry in entries:
            name = self._join([*parts, *self._split(entry["name"])[n:]])
            out[name] = {**entry, "name": name, "islink": False}
        for child in implied:
            name = self._join([*parts, child])
            out.setdefault(name, {"name": name, "type": "directory", "size": 0})
        for key in links:
            name = self._join([*parts, self._split(key)[-1]])
            try:
                size = self.info(key)["size"]
            except OSError:
                size = 0  # dangling or looping symlink
            out[name] = {
                "name": name,
                "type": "other",
                "size": size,
                "islink": True,
                "destination": self.mapping[key],
            }
        if detail:
            return list(out.values())
        return list(out)

    def _open(
        self,
        path: str,
        mode: str = "rb",
        block_size: int | None = None,
        autocommit: bool = True,
        cache_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.fs.open(
            self._resolve(path),
            mode=mode,
            block_size=block_size,
            autocommit=autocommit,
            cache_options=cache_options,
            **kwargs,
        )

    def cat_file(
        self, path: str, start: int | None = None, end: int | None = None, **kwargs
    ) -> bytes:
        return self.fs.cat_file(self._resolve(path), start=start, end=end, **kwargs)

    def pipe_file(self, path: str, value: bytes, **kwargs: Any) -> None:
        self.fs.pipe_file(self._resolve(path), value, **kwargs)

    def cp_file(self, path1: str, path2: str, **kwargs: Any) -> None:
        self.fs.cp_file(self._resolve(path1), self._resolve(path2), **kwargs)

    def mkdir(self, path: str, create_parents: bool = True, **kwargs: Any) -> None:
        if self.islink(path):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)
        self.fs.mkdir(self._link_key(path), create_parents=create_parents, **kwargs)

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        if self.islink(path):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)
        self.fs.makedirs(self._link_key(path), exist_ok=exist_ok)

    def rmdir(self, path: str) -> None:
        if self.islink(path):
            raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), path)
        self.fs.rmdir(self._link_key(path))

    def rm_file(self, path: str) -> None:
        key = self._link_key(path)
        if key in self.mapping:
            del self.mapping[key]
        else:
            self.fs.rm_file(key)

    def rm(
        self,
        path: str | list[str],
        recursive: bool = False,
        maxdepth: int | None = None,
    ) -> None:
        for p in [path] if isinstance(path, str) else path:
            key = self._link_key(p)
            if key in self.mapping:
                del self.mapping[key]
                continue
            self.fs.rm(key, recursive=recursive, maxdepth=maxdepth)
            if recursive:
                prefix = key.rstrip("/") + "/"
                for k in [k for k in self.mapping if k.startswith(prefix)]:
                    del self.mapping[k]

    def mv(self, path1: str, path2: str, **kwargs: Any) -> None:
        src = self._link_key(path1)
        dst = self._link_key(path2)
        if src in self.mapping:
            self.mapping[dst] = self.mapping.pop(src)
            return
        self.fs.mv(src, dst, **kwargs)
        prefix = src.rstrip("/") + "/"
        for k in [k for k in self.mapping if k.startswith(prefix)]:
            self.mapping[dst.rstrip("/") + "/" + k[len(prefix) :]] = self.mapping.pop(k)
