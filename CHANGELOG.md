# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed
- Renamed `watchdog.py` to `speed_watchdog.py`, so an install of this tool cannot shadow the widely used `watchdog` package; the hint lines in `report` now name the command you typed instead of a fixed file name.

## [1.1.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added a terminal demo to the README's first screen, showing watchdog.py validate and report, catching one hook thirty-four percent slower than its frozen baseline.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

## [1.0.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.0.0) - 2026-08-31

First public release.
