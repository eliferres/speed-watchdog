# Changelog

## Unreleased

Nothing yet.

## [1.2.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.2.0) - 2026-10-02

### Added
- Installable with `pipx install git+https://github.com/eliferres/speed-watchdog`, which puts a `speed-watchdog` command on your path; `speed-watchdog --version` prints the version.

### Fixed
- A `NaN` or `Infinity` in the config, the baseline or a history row no longer silences alarms: the config and baseline are refused with exit 2 and the history row is skipped; `history` and `baseline` must be paths, so `"baseline": 5` is refused too.
- A config file that cannot be read or is not UTF-8 no longer crashes with a traceback: it prints one line on stderr naming the file and exits 2.
- `report` no longer crashes on a probe whose baseline median is 0 ms: it prints a `WARN` line for that probe and skips the percentage.
- `report` with a `baseline.json` that will not parse, or that holds a median that is not a number, no longer crashes with a traceback: it prints one line on stderr naming the file and exits 2.
- The walkthrough no longer says the README has no demo picture; it now says the picture at the top shows its first two steps.
- The demo transcript and the terminal picture now show the report's full output, including the payload_check line that was missing, and a test replays every demo command to keep them honest.
- The demo picture no longer cuts its long lines off at the right edge: rows wider than the box ran past it mid-word with no ellipsis. Only the drawing changed; the recorded session is untouched.

### Changed
- A missing or malformed config and a `--now` that is not an ISO date now exit 2 with the message on stderr, where they exited 1 on stdout like an alarm, so a scheduler can tell a broken setup from a slower one; the README now lists every exit code, including 2 for a command line the parser rejects, in a table.
- The README badge row now shows the license, the lowest supported Python and that there are no dependencies beside the CI status, above the demo picture.
- Renamed `watchdog.py` to `speed_watchdog.py`, so an install of this tool cannot shadow the widely used `watchdog` package; the hint lines in `report` now name the command you typed instead of a fixed file name.
- The README now says what a report with only `WARN` lines does today: the verdict line still reads `PASS` and the exit code is still 0.
- The README leads with installing, and the walkthrough, the config reference and what the report refuses now sit under headings that say what they hold.

## [1.1.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added a terminal demo to the README's first screen, showing watchdog.py validate and report, catching one hook thirty-four percent slower than its frozen baseline.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

## [1.0.0](https://github.com/eliferres/speed-watchdog/releases/tag/v1.0.0) - 2026-08-31

First public release.
