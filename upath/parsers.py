"""upath.parsers -- path parsers for UPath implementations

A parser implements the lexical operations (splitting, joining, stripping
protocols, ...) for the paths of a UPath subclass. Each UPath subclass
exposes its parser via the `parser` class attribute.

Customize how a UPath subclass parses its paths by setting `parser`:

```python
from upath.implementations.cloud import S3Path
from upath.parsers import FSSpecParser


class FooPath(S3Path):
    parser = FSSpecParser("s3", protocol="foo")
```

!!! warning "experimental"
    This module is experimental and its API might still change.
"""

from __future__ import annotations

from upath._flavour import FSSpecParser

__all__ = [
    "FSSpecParser",
]
