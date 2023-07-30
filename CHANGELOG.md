# universal_pathlib changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Changed
- updated past changelog entries.

### Fixed
- improved azure test separation (#123).

## [0.0.24] - 2023-06-19
### Added
- started a changelog to keep track of significant changes (#118).
- add support for abfss protocol (#113).
- add cpython pathlib tests (#104).
- implemented `.rename` (#96).

### Fixed
- various webdav test fixes (#103, #107, #109).
- fixed issue with `._url` parsing (#102).
- improved error messages (#96).
- fixed `.rglob()` method (#96).

### Changed
- modernized package dev tools (#105).
- updated ipynb example notebook (#96).

## [0.0.23] - 2023-03-24
### Added
- Implement `UPath.resolve` with a special redirect-following implementation for `HTTPPath` (#86).

## [0.0.22] - 2023-03-11
### Fixed
- Respect exist_ok in mkdir when creating parent directories (#83).

## [0.0.21] - 2022-09-19
### Changed
- Changed the `UPath` implementation registry to lazily import implementations (#78).
- Refactored class methods (#77).

### Fixed
- Fixed S3 paths with a `+` (#76).

## [0.0.20] - 2022-08-30
### Added
- Python 3.11 compatibility (#69).

### Fixed
- Fix `.parents` (#75).
- Fix `.with_*` methods (#73).

### Changed
- Use `NotADirectoryError` instead of custom error (#74).

## [0.0.19] - 2022-06-22
### Added
- started a changelog to keep track of significant changes

[Unreleased]: https://github.com/fsspec/universal_pathlib/compare/v0.0.24...HEAD
[0.0.24]: https://github.com/fsspec/universal_pathlib/compare/v0.0.23...v0.0.24
[0.0.23]: https://github.com/fsspec/universal_pathlib/compare/v0.0.22...v0.0.23
[0.0.22]: https://github.com/fsspec/universal_pathlib/compare/v0.0.21...v0.0.22
[0.0.21]: https://github.com/fsspec/universal_pathlib/compare/v0.0.20...v0.0.21
[0.0.20]: https://github.com/fsspec/universal_pathlib/compare/v0.0.19...v0.0.20
[0.0.19]: https://github.com/fsspec/universal_pathlib/tree/v0.0.19