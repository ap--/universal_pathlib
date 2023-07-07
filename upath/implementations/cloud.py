from __future__ import annotations

from upath.core import FSSpecUPath


class CloudPath(FSSpecUPath):
    __slots__ = ()


class GCSPath(CloudPath):
    __slots__ = ()


class S3Path(CloudPath):
    __slots__ = ()


class AzurePath(CloudPath):
    __slots__ = ()
