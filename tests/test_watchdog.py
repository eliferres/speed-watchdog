"""Tests for watchdog.

Every case builds a real config and a real history on disk and runs the
real code against it - no mocks. The probe commands are shell no-ops, so
the whole suite costs milliseconds. One differential case runs the shipped
demo end to end through the CLI: the demo in this repo must always produce
the alarm its README claims.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import watchdog  # noqa: E402


def write_config(root: Path, probes=None, **overrides) -> Path:
    config = {
        "runs_per_probe": 3,
        "window_days": 7,
        "probes": probes if probes is not None else [
            {"name": "fast", "command": ":", "unit": "ms", "threshold_pct": 20},
        ],
    }
    config.update(overrides)
    path = root / "watchdog.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def write_history(root: Path, rows) -> None:
    lines = [
        json.dumps({"ts": ts, "probe": probe, "median_ms": ms, "runs": 3})
        for ts, probe, ms in rows
    ]
    (root / "history.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_baseline(root: Path, medians, set_at="2026-06-01") -> Path:
    path = root / "baseline.json"
    path.write_text(json.dumps({"set_at": set_at, "window_days": 7, "medians": medians}),
                    encoding="utf-8")
    return path


def run_cli(*argv):
    """Runs main() in-process and returns (exit_code, stdout)."""
    from contextlib import redirect_stdout
    from io import StringIO

    buffer = StringIO()
    with redirect_stdout(buffer):
        code = watchdog.main(list(argv))
    return code, buffer.getvalue()


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    # ---- the shipped demo ----

    def test_shipped_demo_report_alarms(self):
        # The README's headline claim, end to end through the CLI.
        proc = subprocess.run(
            [sys.executable, str(REPO / "watchdog.py"), "report",
             "--config", str(REPO / "demo" / "watchdog.json"), "--now", "2026-06-14"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ALARM context_inject", proc.stdout)
        self.assertIn("ok    rules_lint", proc.stdout)

    # ---- median math ----

    def test_median_ignores_one_slow_outlier(self):
        entries = watchdog.read_history(self.write_rows([
            ("2026-06-10T02:00:00", "fast", 10.0),
            ("2026-06-11T02:00:00", "fast", 900.0),
            ("2026-06-12T02:00:00", "fast", 11.0),
        ]))
        medians = watchdog.window_medians(entries, datetime(2026, 6, 12), 7)
        self.assertEqual(medians["fast"], (11.0, 3))

    def test_median_of_even_count_averages_the_middle_pair(self):
        entries = watchdog.read_history(self.write_rows([
            ("2026-06-10T02:00:00", "fast", 10.0),
            ("2026-06-11T02:00:00", "fast", 20.0),
            ("2026-06-12T02:00:00", "fast", 30.0),
            ("2026-06-13T02:00:00", "fast", 60.0),
        ]))
        medians = watchdog.window_medians(entries, datetime(2026, 6, 13), 7)
        self.assertEqual(medians["fast"], (25.0, 4))

    # ---- alarms ----

    def test_alarm_fires_above_threshold(self):
        config = write_config(self.root)
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 13.0)])
        write_baseline(self.root, {"fast": 10.0})
        code, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 1, out)
        self.assertIn("ALARM fast", out)

    def test_no_alarm_just_below_threshold(self):
        config = write_config(self.root)
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 11.9)])
        write_baseline(self.root, {"fast": 10.0})
        code, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_report_without_a_baseline_refuses(self):
        config = write_config(self.root)
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 11.0)])
        code, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 1)
        self.assertIn("no baseline yet", out)

    # ---- the baseline moves only on command ----

    def test_report_and_run_never_move_the_baseline(self):
        config = write_config(self.root)
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 99.0)])
        baseline = write_baseline(self.root, {"fast": 10.0})
        frozen = baseline.read_text(encoding="utf-8")

        run_cli("report", "--config", str(config), "--now", "2026-06-12")
        run_cli("run", "--config", str(config), "--runs", "1")
        self.assertEqual(baseline.read_text(encoding="utf-8"), frozen)

        code, _ = run_cli("baseline", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 0)
        self.assertNotEqual(baseline.read_text(encoding="utf-8"), frozen)

    def test_baseline_freezes_the_window_median(self):
        config = write_config(self.root)
        write_history(self.root, [
            ("2026-06-10T02:00:00", "fast", 10.0),
            ("2026-06-11T02:00:00", "fast", 20.0),
            ("2026-06-12T02:00:00", "fast", 12.0),
            ("2026-05-01T02:00:00", "fast", 500.0),  # outside the window
        ])
        code, out = run_cli("baseline", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 0, out)
        written = json.loads((self.root / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(written["medians"], {"fast": 12.0})
        self.assertEqual(written["set_at"], "2026-06-12")

    # ---- gaps are reported, never fatal ----

    def test_probe_missing_from_history_warns_without_crashing(self):
        config = write_config(self.root, probes=[
            {"name": "fast", "command": ":", "threshold_pct": 20},
            {"name": "never_ran", "command": ":", "threshold_pct": 20},
        ])
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 10.0)])
        write_baseline(self.root, {"fast": 10.0})
        code, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 0, out)
        self.assertIn("WARN  never_ran", out)

    def test_torn_history_line_is_skipped(self):
        config = write_config(self.root)
        (self.root / "history.jsonl").write_text(
            json.dumps({"ts": "2026-06-12T02:00:00", "probe": "fast",
                        "median_ms": 10.0, "runs": 3}) + '\n{"ts": "2026-06-13T0',
            encoding="utf-8")
        write_baseline(self.root, {"fast": 10.0})
        code, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(code, 0, out)
        self.assertIn("1 runs", out)

    # ---- --now ----

    def test_now_decides_what_is_in_the_window(self):
        config = write_config(self.root)
        write_history(self.root, [("2026-06-12T02:00:00", "fast", 40.0)])
        write_baseline(self.root, {"fast": 10.0})

        alarming, out = run_cli("report", "--config", str(config), "--now", "2026-06-12")
        self.assertEqual(alarming, 1, out)

        # Same history, a month later: the run has aged out of the window.
        clean, out = run_cli("report", "--config", str(config), "--now", "2026-07-12")
        self.assertEqual(clean, 0, out)
        self.assertIn("WARN  fast", out)

    # ---- run ----

    def test_run_records_one_line_per_probe(self):
        config = write_config(self.root, probes=[
            {"name": "a", "command": ":", "threshold_pct": 20},
            {"name": "b", "command": ":", "threshold_pct": 20},
        ])
        code, out = run_cli("run", "--config", str(config), "--runs", "3")
        self.assertEqual(code, 0, out)
        rows = [json.loads(line) for line in
                (self.root / "history.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["probe"] for r in rows], ["a", "b"])
        self.assertTrue(all(r["runs"] == 3 and r["median_ms"] > 0 for r in rows))

    def test_run_fails_loudly_when_a_probe_command_fails(self):
        config = write_config(self.root, probes=[
            {"name": "broken", "command": "exit 3", "threshold_pct": 20},
        ])
        code, out = run_cli("run", "--config", str(config), "--runs", "1")
        self.assertEqual(code, 1)
        self.assertIn("exited 3", out)
        self.assertFalse((self.root / "history.jsonl").read_text(encoding="utf-8").strip())

    # ---- validate ----

    def test_validate_rejects_broken_json(self):
        path = self.root / "watchdog.json"
        path.write_text("{not json", encoding="utf-8")
        code, out = run_cli("validate", "--config", str(path))
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", out)

    def test_validate_rejects_malformed_probes(self):
        cases = {
            "threshold_pct": [{"name": "a", "command": ":"}],
            "duplicate probe name": [
                {"name": "a", "command": ":", "threshold_pct": 5},
                {"name": "a", "command": ":", "threshold_pct": 5},
            ],
            "command must be": [{"name": "a", "command": "", "threshold_pct": 5}],
            "name must be": [{"command": ":", "threshold_pct": 5}],
        }
        for expected, probes in cases.items():
            with self.subTest(expected=expected):
                errors = watchdog.validate_config({"probes": probes})
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_validate_accepts_the_shipped_demo_config(self):
        code, out = run_cli("validate", "--config", str(REPO / "demo" / "watchdog.json"))
        self.assertEqual(code, 0, out)
        self.assertIn("3 probes", out)

    # ---- helpers ----

    def write_rows(self, rows) -> Path:
        write_history(self.root, rows)
        return self.root / "history.jsonl"


if __name__ == "__main__":
    unittest.main()
