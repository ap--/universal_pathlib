from __future__ import annotations

from fsspec.asyn import sync

from upath.core import FSSpecUPath


class HTTPPath(FSSpecUPath):
    __slots__ = ()
    # _default_accessor = _HTTPAccessor

    def is_dir(self):
        try:
            return self._path_type() == "directory"
        except FileNotFoundError:
            return False

    def is_file(self):
        try:
            return self._path_type() == "file"
        except FileNotFoundError:
            return False

    def _path_type(self):
        try:
            next(iter(self.fs.ls(self.path, detail=False)))
        except (StopIteration, NotADirectoryError):
            return "file"
        else:
            return "directory"

    def resolve(
        self: HTTPPath, strict: bool = False, follow_redirects: bool = True
    ) -> HTTPPath:
        """Normalize the path and resolve redirects."""
        # Normalise the path
        resolved_path = super().resolve(strict=strict)

        if follow_redirects:
            # Ensure we have a url
            parsed_url = resolved_path._url
            if parsed_url is None:
                return resolved_path
            else:
                url = parsed_url.geturl()
            # Get the fsspec fs
            fs = resolved_path.fs
            # Ensure we have a session
            session = sync(fs.loop, fs.set_session)
            # Use HEAD requests if the server allows it, falling back to GETs
            for method in (session.head, session.get):
                r = sync(fs.loop, method, url, allow_redirects=True)
                try:
                    r.raise_for_status()
                except Exception as exc:
                    if method == session.get:
                        raise FileNotFoundError(self) from exc
                else:
                    resolved_path = HTTPPath(str(r.url))
                    break

        return resolved_path
