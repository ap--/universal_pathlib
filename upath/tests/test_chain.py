from upath import UPath


def test_chained_path(tmp_path):
    pth = tmp_path.joinpath("abc.txt")
    pth.write_text("hello world")
    uri = pth.as_uri()

    p = UPath(f"simplecache::{uri}")
    assert p.read_text() == "hello world"
