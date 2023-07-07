from __future__ import annotations

from upath.core import FSSpecUPath

__all__ = ["MemoryPath"]


class MemoryPath(FSSpecUPath):
    __slots__ = ()

    @classmethod
    def cwd(cls):
        raise NotImplementedError(f"unsupported for {cls.__name__}")

    @classmethod
    def home(cls):
        raise NotImplementedError(f"unsupported for {cls.__name__}")

    def chmod(self, mode, *, follow_symlinks=True):
        raise NotImplementedError(f"unsupported for {type(self).__name__}")

    def expanduser(self):
        raise NotImplementedError(f"unsupported for {type(self).__name__}")

    def group(self):
        raise NotImplementedError(f"unsupported for {type(self).__name__}")
