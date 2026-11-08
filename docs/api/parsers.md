# Parsers :scissors:

A parser implements the lexical path operations of a UPath subclass: stripping the
protocol, splitting a path into its drive, root and parts, and joining segments. Every
UPath subclass exposes its parser via the `parser` attribute.

!!! warning "Experimental"
    The parser API is experimental and might still change in future releases.

## FSSpecParser

::: upath.parsers.FSSpecParser
    options:
        heading_level: 3
        show_root_heading: true
        show_root_full_path: false
        members: false
        show_bases: false

---

## Usage Example

By default, a UPath subclass parses paths using the fsspec filesystem registered for
its protocol. Set a custom `parser` if your filesystem should parse paths differently,
for example like an object store, where the bucket is the anchor of every path and keys
may contain empty segments.

### Parse a custom protocol like an existing one

```python
from upath import UPath
from upath.implementations.cloud import S3Path
from upath.parsers import FSSpecParser
from upath.registry import register_implementation


class MyProtoPath(S3Path):
    parser = FSSpecParser("s3", protocol="myproto")


register_implementation("myproto", MyProtoPath)

p = UPath("myproto://bucket/dir/file.txt")
assert p.parts == ("bucket/", "dir", "file.txt")
assert p.anchor == "bucket/"
```

### Build a parser from your filesystem class

The parser uses the `_strip_protocol`, `_get_kwargs_from_urls` and `_parent`
classmethods and the `protocol`, `root_marker` and `sep` attributes of the filesystem
class. Parts implemented as instance methods or properties fall back to the
`fsspec.AbstractFileSystem` defaults. The parser options default to the settings
universal_pathlib uses for the filesystem's protocol, so set them explicitly for new
protocols:

```python
from fsspec.spec import AbstractFileSystem

from upath.implementations.cloud import S3Path
from upath.parsers import FSSpecParser


class MyProtoFileSystem(AbstractFileSystem):
    protocol = "myproto"
    root_marker = ""


class MyProtoPath(S3Path):
    parser = FSSpecParser(
        MyProtoFileSystem,
        netloc_is_anchor=True,  # the bucket is the anchor
        supports_empty_parts=True,  # "bucket/a//b" != "bucket/a/b"
    )
```

---

## See Also :link:

- [Registry](registry.md) - Register your UPath subclass for a protocol
- [Implementations](implementations.md) - Built-in UPath subclasses
