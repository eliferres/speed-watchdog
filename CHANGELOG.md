# Changelog

## Unreleased

### Added
- Installable with `pipx install git+https://github.com/eliferres/speed-watchdog`, which puts a `speed-watchdog` command on your path; `speed-watchdog --version` prints the version.

### Fixed
- The walkthrough no longer says the README has no demo picture; it now says the picture at the top shows its first two steps.
- The demo transcript and the terminal picture now show the report's full output, including the payload_check line that was missing, and a test replays every demo command to keep them honest.
- The demo picture no longer cuts its long lines off at the right edge: rows wider than the box ran past it mid-word with no ellipsis. Only the drawing changed; the recorded session is untouched.

### Changed
- Renamed `watchdog.py` to `speed_watchdog.py`, so an install of this tool cannot shadow the widely used `watchdog` package; the hint lines in `report` now name the command you typed instead of a fixed file name.
- The README's exit-code sentence now lists exit 2, which is what a command line the parser rejects returns; it previously listed 0 and 1 only.
- The README now says what a report with only `WARN` lines does today: the verdict line still reads `PASS` and the exit code is still 0.
- The README leads with installing, and the walkthrough, the config reference and what the report refuses now sit under headings that say what they hold.

## [1.1.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added a terminal demo to the README's first screen, showing watchdog.py validate and report, catching one hook thirty-four percent slower than its frozen baseline.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

## [1.0.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.0.0) - 2026-08-31

First public release.
