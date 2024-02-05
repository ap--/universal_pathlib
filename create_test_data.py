# create test data folder for github filesystem

import pathlib


def local_testdir(tmp_path):
    folder1 = tmp_path.joinpath("folder1")
    folder1.mkdir()
    folder1_files = ["file1.txt", "file2.txt"]
    for f in folder1_files:
        p = folder1.joinpath(f)
        p.touch()
        p.write_text(f)

    file1 = tmp_path.joinpath("file1.txt")
    file1.touch()
    file1.write_text("hello world")
    file2 = tmp_path.joinpath("file2.txt")
    file2.touch()
    file2.write_bytes(b"hello world")


data_dir = pathlib.Path(__file__).parent.joinpath("data")

local_testdir(data_dir)
