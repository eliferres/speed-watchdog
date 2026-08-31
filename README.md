# speed-watchdog

An agent harness gets slow the way a house gets cluttered: one hook, one
gate, one "tiny" startup file at a time, each too small to argue with.
Six months later every turn drags and nobody can say when it happened.
This is the meter that can. Probes are plain commands whose wall-clock
time is the metric, so it works on any harness. It records medians,
compares them against a baseline that moves only when you say so, and
exits non-zero the day something got slower.

Python 3.9+, standard library only, one file.

![ci](https://github.com/eliferres/speed-watchdog/actions/workflows/ci.yml/badge.svg)

## Quick start

```bash
git clone https://github.com/eliferres/speed-watchdog.git
cd speed-watchdog
python3 watchdog.py validate --config demo/watchdog.json
python3 watchdog.py report   --config demo/watchdog.json --now 2026-06-14
```

That second command reads 14 days of canned history shipped in `demo/`
and exits 1, because one of the demo's fictional hooks got slower. The
[walkthrough](#the-walkthrough) below runs the whole loop offline. Then
point `probes` at your own harness and put `run` on a nightly schedule.

## The four ideas

**A probe is a command.** Whatever you can time from a shell, you can
meter: a hook chain against a canned payload, a cold CLI start, a lint of
the rules file. No integration, no instrumentation inside the harness,
nothing to keep in sync with it. The command's wall-clock time *is* the
number.

**Medians, never means.** Each run times every probe K times (default 3)
and records the median. One GC pause, one cold cache, one noisy neighbour
on the machine, and a mean would report a regression that is not there.
The median throws that sample away. The report medians again across the
window, so a whole bad night cannot move the verdict on its own.

**Frozen baselines.** The comparison point lives in `baseline.json` and
changes only when a human runs `watchdog.py baseline`. A baseline that
slid with a rolling average would absorb the exact drift it exists to
catch: every day is 2% slower than yesterday, nothing ever alarms, and a
year later everything takes twice as long.

**A date, not a shrug.** Because history is append-only and dated, "when
did this get slow" has an answer you can read off `trend`. That only
holds if the meter runs on a schedule and every addition to the harness
arrives with a probe. The tool cannot enforce that part; you do.

## The config, verbatim

One probe entry is the whole contract. This is `demo/watchdog.json`,
trimmed to one probe:

```json
{
  "runs_per_probe": 3,
  "window_days": 7,
  "timeout_s": 30,
  "history": "history.jsonl",
  "baseline": "baseline.json",
  "probes": [
    {
      "name": "context_inject",
      "command": "sh hooks/inject-context.sh",
      "unit": "wall-clock ms for the context-injection hook on one canned turn",
      "threshold_pct": 20
    }
  ]
}
```

`name`, `command`, and `threshold_pct` are required; everything else has
the default shown above. Paths are relative to the config file, and
commands run with the config file's directory as their working
directory, so a checked-in config works from anywhere.

Each `run` appends one line per probe to the history, and that line is
the entire storage format:

```json
{"ts": "2026-06-14T02:00:00", "probe": "context_inject", "median_ms": 96.2, "runs": 3}
```

## The walkthrough

Every command below runs from a fresh clone with no setup. There is no
animated demo on purpose: the demo is executable, so you can check these
numbers instead of watching them.

**1. Lint the config.** What each probe measures, in plain words, and
where it alarms:

```console
$ python3 watchdog.py validate --config demo/watchdog.json
config OK: 3 probes, 3 runs each, 7-day window
  rules_lint  (alarm at +20%)
    measures: wall-clock ms to read and lint the rules file at session start
    command:  sh hooks/load-rules.sh
  payload_check  (alarm at +20%)
    measures: wall-clock ms for the pre-tool hook to inspect one canned tool call
    command:  sh hooks/check-payload.sh
  context_inject  (alarm at +20%)
    measures: wall-clock ms for the context-injection hook on one canned turn
    command:  sh hooks/inject-context.sh
```

**2. Read the report.** `--now` anchors the window to the canned history
so the output is the same on every machine and in every year:

```console
$ python3 watchdog.py report --config demo/watchdog.json --now 2026-06-14
speed-watchdog  window=7d  now=2026-06-14  baseline frozen 2026-06-05
  ok    rules_lint               recent     18.1 ms   baseline     18.0 ms     +0.6%  (limit +20%, 7 runs)
  ok    payload_check            recent     42.0 ms   baseline     41.9 ms     +0.2%  (limit +20%, 7 runs)
  ALARM context_inject           recent     80.4 ms   baseline     60.1 ms    +33.8%  (limit +20%, 7 runs)
ALARM: 1 probe(s) slower than the frozen baseline. Find what was added, or re-baseline deliberately.
$ echo $?
1
```

**3. See when it happened.** Full height is one alarm threshold, so
jitter stays flat and only real drift climbs:

```console
$ python3 watchdog.py trend --config demo/watchdog.json
speed-watchdog trend  (42 recorded runs, oldest first)
  rules_lint   (full height = +20%, its alarm threshold)
    ._.._.._..__..  17.9 -> 18.1 ms (min 17.6, max 18.5, 14 runs)
  payload_check   (full height = +20%, its alarm threshold)
    ..._......._..  41.6 -> 41.5 ms (min 41.4, max 42.9, 14 runs)
  context_inject   (full height = +20%, its alarm threshold)
    ........._=+*#  59.4 -> 96.2 ms (min 59.4, max 96.2, 14 runs)
```

Flat, flat, and a ramp starting on day ten. That is the date the report
could not give you.

**4. Meter for real.** This times the demo's shell hooks on your machine
and appends today's rows, so your numbers will differ from these - the
demo hooks sleep, and your process-spawn cost is your own:

```console
$ python3 watchdog.py run --config demo/watchdog.json
  rules_lint                    22.7 ms   (median of 3)
  payload_check                 51.1 ms   (median of 3)
  context_inject               115.5 ms   (median of 3)
OK: 3 probes recorded to history.jsonl at 2026-08-30T21:09:58
```

Run it after step 3, not before: the rows it writes are dated today, so
they stay outside the June 2026 window every other step reads.

**5. Re-baseline deliberately.** You looked, you found the second lookup
pass someone added to `demo/hooks/inject-context.sh`, and you decided to
keep it. Only now does the number move:

```console
$ python3 watchdog.py baseline --config demo/watchdog.json --now 2026-06-14
  context_inject                80.4 ms   (median of 7 runs)
  payload_check                 42.0 ms   (median of 7 runs)
  rules_lint                    18.1 ms   (median of 7 runs)
OK: baseline frozen at 2026-06-14 in baseline.json
```

**6. Clean.** Same history, same window, new frozen baseline:

```console
$ python3 watchdog.py report --config demo/watchdog.json --now 2026-06-14
speed-watchdog  window=7d  now=2026-06-14  baseline frozen 2026-06-14
  ok    rules_lint               recent     18.1 ms   baseline     18.1 ms     +0.0%  (limit +20%, 7 runs)
  ok    payload_check            recent     42.0 ms   baseline     42.0 ms     +0.0%  (limit +20%, 7 runs)
  ok    context_inject           recent     80.4 ms   baseline     80.4 ms     +0.0%  (limit +20%, 7 runs)
PASS: no probe over its threshold.
$ echo $?
0
```

`git checkout demo/` puts the demo back for the next reader.

## What is in the box

| Path | Role |
|---|---|
| `watchdog.py` | The whole tool: `run`, `report`, `baseline`, `trend`, `validate`. |
| `demo/watchdog.json` | A worked config: three probes, thresholds, units. |
| `demo/history.jsonl` | 14 canned days, one probe regressing on day ten. |
| `demo/baseline.json` | The frozen comparison point, set 2026-06-05. |
| `demo/hooks/` | A fictional harness: three shell hooks with known costs. |
| `tests/test_watchdog.py` | Real configs and histories in temp dirs, no mocks. |

## Wiring it in

Point `probes` at your own harness, take a week of nightly runs, then
freeze:

```bash
python3 watchdog.py baseline --config watchdog.json
```

A nightly `run`, and a `report` that anyone will see when it fails:

```cron
0 3 * * *  cd /path/to/harness && python3 watchdog.py run    --config watchdog.json
5 3 * * *  cd /path/to/harness && python3 watchdog.py report --config watchdog.json
```

`report` exits 1 on any alarm, so cron mails it, CI fails on it, and a
wrapper script can page on it. Exit codes across the board: 0 clean, 1
for an alarm, a broken probe command, a malformed config, or a missing
baseline.

## What the report will not let you get away with

- **A baseline that drifts.** Nothing except `baseline` writes
  `baseline.json`. There is no auto-update flag to turn on in a hurry.
- **A silent gap.** A probe with no runs in the window is printed as a
  `WARN` line, so a meter that quietly stopped is visible rather than
  reported as healthy.
- **A one-night fluke.** Two layers of median - across the K runs and
  across the window's days - stand between a slow night and an alarm.
- **An unreadable history.** One JSON object per line, dated, with the
  run count. Any tool you already have can read it.

## Limitations

- Wall-clock on a busy machine is noisy. Medians absorb the spikes, not
  a sustained load: metering during a build will look like a regression.
  Meter on an idle machine, at the same hour.
- It times commands. Overhead that lives inside a long-running process
  is invisible unless you write a probe that exercises it from outside.
- A probe suite only covers what somebody thought to meter. The
  regression that hides in the gap will not alarm, which is why a new
  hook should arrive with its probe.
- Thresholds are percentages of a baseline. On a probe that measures 5ms,
  20% is a millisecond of noise; set thresholds from the spread you
  actually observe in `trend`, not from a round number.
- One machine, one history file. Comparing numbers across machines with
  different hardware is not meaningful, and the tool does not try.

## License

MIT
