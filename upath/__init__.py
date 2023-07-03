"""Pathlib API extended to use fsspec backends."""
from typing import TYPE_CHECKING

try:
    from upath._version import __version__
except ImportError:
    __version__ = "not-installed"


__all__ = ["UPath"]

if TYPE_CHECKING:
    from upath.core import UPath


def __getattr__(name):
    if name == "UPath":
        from upath.core import UPath

        return UPath
    else:
        raise AttributeError(name)
