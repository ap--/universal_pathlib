import pytest

from upath import UPath
from upath.implementations.memory import MemoryPath

from ..cases import BaseTests


class TestMemoryPath(BaseTests):
    @pytest.fixture(autouse=True)
    def path(self, local_testdir):
        if not local_testdir.startswith("/"):
            local_testdir = "/" + local_testdir
        path = f"memory:/{local_testdir}"
        self.path = UPath(path)
        self.prepare_file_system()

    def test_is_MemoryPath(self):
        assert isinstance(self.path, MemoryPath)


NORMALIZATIONS = (
    ("unnormalized", "normalized"),
    (
        # Normalization with and without an authority component
        ("memory:/a/b/..", "memory:/a/"),
        ("memory:/a/b/../..", "memory:/"),
        ("memory:/a/b/../../..", "memory:/"),
        ("memory://a/b/..", "memory://a/"),
        ("memory://a/b/../..", "memory://a/"),
        ("memory://a/b/../../..", "memory://a/"),
    ),
)


@pytest.mark.parametrize(*NORMALIZATIONS)
def test_normalize(unnormalized, normalized):
    expected = str(UPath(normalized))
    result = str(UPath.resolve(UPath(unnormalized)))
    assert expected == result
