from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from upath.core import UPath


def skip_on_windows(func):
    return pytest.mark.skipif(
        sys.platform.startswith("win"), reason="Don't run on Windows"
    )(func)


def only_on_windows(func):
    return pytest.mark.skipif(
        not sys.platform.startswith("win"), reason="Only run on Windows"
    )(func)


def posixify(path):
    return str(path).replace("\\", "/")


def exact_equal(p0: UPath, p1: UPath) -> bool:
    """ensure two paths are (almost) exactly the same"""
    unset = ...
    assert type(p0) == type(p1)
    assert str(p0) == str(p1)
    for cls in type(p0).mro():
        for slot in getattr(cls, "__slots__", []):
            if slot == "_raw_paths":
                continue
            p0_slot = getattr(p0, slot, unset)
            p1_slot = getattr(p1, slot, unset)
            assert p0_slot == p1_slot

    assert p0.fs == p1.fs
    assert p0.fs.storage_options == p1.fs.storage_options

    return True
