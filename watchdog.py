#!/usr/bin/env python3
"""speed-watchdog - a meter for an agent harness's own overhead.

Every probe is a command whose wall-clock time IS the metric, so this
meters any harness: a hook chain against a canned payload, a cold CLI
start, a rules-file lint. Each run times every probe K times and records
the MEDIAN, because one GC pause or cold cache must never look like a
regression. The report compares the recent median against a frozen
baseline that moves only when a human runs `baseline`.

Stdlib only. Exit 1 on any alarm or error, 0 clean.

Usage:
    python watchdog.py validate [--config watchdog.json]
    python watchdog.py run      [--config ...] [--runs K]
    python watchdog.py report   [--config ...] [--now ISO-DATE]
    python watchdog.py baseline [--config ...] [--now ISO-DATE]
    python watchdog.py trend    [--config ...]
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

DEFAULTS = {
    "runs_per_probe": 3,
    "window_days": 7,
    "timeout_s": 60,
    "history": "history.jsonl",
    "baseline": "baseline.json",
}

# Seven levels is as much resolution as a monospace column can carry
# honestly; the printed min/max carries the real numbers.
LEVELS = "._-=+*#"


# ---------- config ----------

def validate_config(raw: dict) -> list[str]:
    errors = []
    probes = raw.get("probes")
    if not isinstance(probes, list) or not probes:
        return ["probes: must be a non-empty list"]

    for key in ("runs_per_probe", "window_days", "timeout_s"):
        if key in raw and (not isinstance(raw[key], (int, float)) or raw[key] < 1):
            errors.append(f"{key}: must be a number >= 1, got {raw[key]!r}")

    seen = set()
    for i, probe in enumerate(probes):
        where = f"probes[{i}]"
        if not isinstance(probe, dict):
            errors.append(f"{where}: must be an object")
            continue
        name = probe.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}: name must be a non-empty string")
        elif name in seen:
            errors.append(f"{where}: duplicate probe name {name!r}")
        else:
            seen.add(name)
        if not isinstance(probe.get("command"), str) or not probe["command"].strip():
            errors.append(f"{where}: command must be a non-empty string")
        threshold = probe.get("threshold_pct")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 0:
            errors.append(f"{where}: threshold_pct must be a number > 0, got {threshold!r}")
        if "unit" in probe and not isinstance(probe["unit"], str):
            errors.append(f"{where}: unit must be a string")
    return errors


def read_config(path: Path):
    """Returns (config, errors). config is None whenever errors is non-empty."""
    if not path.is_file():
        return None, [f"{path}: no such config file"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"{path}: invalid JSON ({exc})"]
    if not isinstance(raw, dict):
        return None, [f"{path}: top level must be an object"]

    errors = validate_config(raw)
    if errors:
        return None, errors

    cfg = dict(DEFAULTS)
    cfg.update(raw)
    cfg["dir"] = path.parent
    return cfg, []


def resolve(cfg: dict, key: str) -> Path:
    # Paths in the config are relative to the config file, so a checked-in
    # config works from any working directory.
    return (cfg["dir"] / cfg[key]).resolve()


# ---------- history ----------

def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def read_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            entry["_ts"] = parse_ts(entry["ts"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # A run killed mid-append leaves a torn last line. Losing one
            # sample is fine; refusing to report for a week is not.
            continue
        entries.append(entry)
    return sorted(entries, key=lambda e: e["_ts"])


def window_medians(entries: list[dict], now: datetime, window_days: int) -> dict:
    """Median of each probe's recorded medians inside the window.

    Compared by calendar day: probes run nightly, so the day is the unit a
    human reasons in and a run drifting an hour later must not fall out.
    """
    first_day = now.date() - timedelta(days=window_days - 1)
    samples: dict = {}
    for entry in entries:
        if first_day <= entry["_ts"].date() <= now.date():
            samples.setdefault(entry["probe"], []).append(entry["median_ms"])
    return {name: (round(statistics.median(v), 1), len(v)) for name, v in samples.items()}


# ---------- probing ----------

def time_command(command: str, cwd: Path, timeout: float):
    """Runs the command once; returns (elapsed_ms, returncode, stderr)."""
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            timeout=timeout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        return timeout * 1000.0, 124, f"timed out after {timeout}s"
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, proc.returncode, proc.stderr.decode("utf-8", "replace").strip()


# ---------- subcommands ----------

def cmd_validate(cfg: dict, args) -> int:
    print(f"config OK: {len(cfg['probes'])} probes, {cfg['runs_per_probe']} runs each, "
          f"{cfg['window_days']}-day window")
    for probe in cfg["probes"]:
        unit = probe.get("unit", "wall-clock time of the command")
        print(f"  {probe['name']}  (alarm at +{probe['threshold_pct']}%)")
        print(f"    measures: {unit}")
        print(f"    command:  {probe['command']}")
    return 0


def cmd_run(cfg: dict, args) -> int:
    runs = args.runs or int(cfg["runs_per_probe"])
    history = resolve(cfg, "history")
    history.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().replace(microsecond=0).isoformat()

    failed = []
    with history.open("a", encoding="utf-8") as out:
        for probe in cfg["probes"]:
            samples = []
            for _ in range(runs):
                elapsed_ms, code, stderr = time_command(
                    probe["command"], cfg["dir"], float(cfg["timeout_s"])
                )
                if code != 0:
                    failed.append(f"{probe['name']}: command exited {code} ({stderr or 'no stderr'})")
                    break
                samples.append(elapsed_ms)
            if len(samples) < runs:
                continue
            median = round(statistics.median(samples), 1)
            out.write(json.dumps(
                {"ts": stamp, "probe": probe["name"], "median_ms": median, "runs": runs}
            ) + "\n")
            print(f"  {probe['name']:<24} {median:>9.1f} ms   (median of {runs})")

    for line in failed:
        print(f"FAIL {line}")
    print(f"{'FAIL' if failed else 'OK'}: {len(cfg['probes']) - len(failed)} probes recorded "
          f"to {history.name} at {stamp}")
    return 1 if failed else 0


def cmd_report(cfg: dict, args) -> int:
    baseline_path = resolve(cfg, "baseline")
    if not baseline_path.is_file():
        print(f"FAIL {baseline_path}: no baseline yet - run `watchdog.py baseline` to freeze one")
        return 1
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    frozen = baseline.get("medians", {})

    now = args.now
    window = int(cfg["window_days"])
    recent = window_medians(read_history(resolve(cfg, "history")), now, window)

    print(f"speed-watchdog  window={window}d  now={now.date()}  "
          f"baseline frozen {baseline.get('set_at', 'unknown')}")

    alarms = 0
    for probe in cfg["probes"]:
        name = probe["name"]
        if name not in recent:
            print(f"  WARN  {name:<24} no runs in the last {window} days")
            continue
        if name not in frozen:
            print(f"  WARN  {name:<24} not in the baseline - re-run `watchdog.py baseline`")
            continue
        median, count = recent[name]
        base = frozen[name]
        delta_pct = (median - base) / base * 100.0
        over = delta_pct > probe["threshold_pct"]
        alarms += over
        print(f"  {'ALARM' if over else 'ok   '} {name:<24} "
              f"recent {median:>8.1f} ms   baseline {base:>8.1f} ms   "
              f"{delta_pct:+6.1f}%  (limit +{probe['threshold_pct']}%, {count} runs)")

    if alarms:
        print(f"ALARM: {alarms} probe(s) slower than the frozen baseline. "
              f"Find what was added, or re-baseline deliberately.")
    else:
        print("PASS: no probe over its threshold.")
    return 1 if alarms else 0


def cmd_baseline(cfg: dict, args) -> int:
    now = args.now
    window = int(cfg["window_days"])
    recent = window_medians(read_history(resolve(cfg, "history")), now, window)
    if not recent:
        print(f"FAIL no runs in the last {window} days - nothing to freeze")
        return 1

    path = resolve(cfg, "baseline")
    path.write_text(json.dumps({
        "set_at": now.date().isoformat(),
        "window_days": window,
        "medians": {name: median for name, (median, _) in sorted(recent.items())},
    }, indent=2) + "\n", encoding="utf-8")

    for name, (median, count) in sorted(recent.items()):
        print(f"  {name:<24} {median:>9.1f} ms   (median of {count} runs)")
    missing = [p["name"] for p in cfg["probes"] if p["name"] not in recent]
    for name in missing:
        print(f"  WARN  {name:<24} no runs in the window - left out of the baseline")
    print(f"OK: baseline frozen at {now.date()} in {path.name}")
    return 0


def spark(values: list[float], threshold_pct: float) -> str:
    """Full height is at least one alarm threshold of drift.

    Scaling to the probe's own min/max instead would blow half a percent of
    jitter up into a mountain, and every flat probe would read as a
    regression. Here, flat looks flat and only real drift climbs.
    """
    low = min(values)
    high = max(max(values), low * (1.0 + threshold_pct / 100.0))
    step = (high - low) / (len(LEVELS) - 1)
    if step < 1e-9:
        return LEVELS[0] * len(values)
    return "".join(LEVELS[int((v - low) / step)] for v in values)


def cmd_trend(cfg: dict, args) -> int:
    entries = read_history(resolve(cfg, "history"))
    by_probe: dict = {}
    for entry in entries:
        by_probe.setdefault(entry["probe"], []).append(entry["median_ms"])

    print(f"speed-watchdog trend  ({len(entries)} recorded runs, oldest first)")
    for probe in cfg["probes"]:
        points = by_probe.get(probe["name"], [])
        if not points:
            print(f"  {probe['name']:<24} no history yet")
            continue
        threshold = probe["threshold_pct"]
        print(f"  {probe['name']}   (full height = +{threshold}%, its alarm threshold)")
        print(f"    {spark(points, threshold)}  {points[0]:.1f} -> {points[-1]:.1f} ms "
              f"(min {min(points):.1f}, max {max(points):.1f}, {len(points)} runs)")
    return 0


COMMANDS = {
    "validate": cmd_validate,
    "run": cmd_run,
    "report": cmd_report,
    "baseline": cmd_baseline,
    "trend": cmd_trend,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sub = subparsers.add_parser(name)
        sub.add_argument("--config", default="watchdog.json", type=Path)
        if name in ("report", "baseline"):
            sub.add_argument("--now", default=None,
                             help="ISO date, so a report over recorded history is reproducible")
        if name == "run":
            sub.add_argument("--runs", default=None, type=int,
                             help="override runs_per_probe for this run")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if getattr(args, "now", None) is not None:
        try:
            args.now = parse_ts(args.now)
        except ValueError:
            print(f"FAIL --now: not an ISO date: {args.now}")
            return 1
    elif hasattr(args, "now"):
        args.now = datetime.now()

    cfg, errors = read_config(args.config)
    if errors:
        for line in errors:
            print(f"FAIL {line}")
        return 1
    return COMMANDS[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
