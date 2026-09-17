"""Tests that the demo transcript and the picture are real output.

demo/transcript.json is the README's walkthrough in machine-readable
form. This runs every command in it again, inside a throwaway copy of
the repository, and fails if the recorded output or exit code has
drifted from what the code now prints. demo/terminal.svg is rendered
from the same file, so its text rows are checked against it too.

To regenerate after a deliberate change:

    UPDATE_DEMO_TRANSCRIPT=1 python3 -m unittest discover -s tests

Never hand-edit demo/transcript.json.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRANSCRIPT = REPO / "demo" / "transcript.json"
PICTURE = REPO / "demo" / "terminal.svg"
CHECKOUT_PLACEHOLDER = "/path/to/checkout"
SKIP = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "build", "dist", "*.egg-info")
SVG_TEXT = "{http://www.w3.org/2000/svg}text"
ELLIPSIS = "…"


def run_entry(cmd: str, root: Path):
    """Runs one transcript command with bash in root; returns (out, status)."""
    proc = subprocess.run(
        ["bash", "-c", cmd],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    out = proc.stdout
    if out.endswith("\n"):
        out = out[:-1]
    # The copy's path is machine-specific, and macOS resolves /var through
    # /private/var, so both forms have to go.
    for path in (str(Path(root).resolve()), str(root)):
        out = out.replace(path, CHECKOUT_PLACEHOLDER)
    return out, proc.returncode


def replay(entries):
    """Runs every entry in order inside one copy of the repo."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        shutil.copytree(REPO, root, ignore=SKIP)
        return [run_entry(entry["cmd"], root) for entry in entries]


def picture_rows():
    """The text rows of the picture, as (class, text), title bar dropped."""
    rows = []
    for element in ET.parse(PICTURE).getroot().iter(SVG_TEXT):
        if element.get("font-size") == "14":
            continue  # the window title bar, not session output
        text = "".join(element.itertext())
        classes = [element.get("class")] + [t.get("class") for t in element]
        rows.append(("cmd" if "p" in classes else element.get("class"), text))
    return rows


def is_prefix(shown: str, real: str) -> bool:
    """A row is the real line, or the real line cut once at the end."""
    if shown == real:
        return True
    head = shown[: -len(ELLIPSIS)]
    return shown.endswith(ELLIPSIS) and shown.count(ELLIPSIS) == 1 and real.startswith(head)


class DemoTranscriptTest(unittest.TestCase):
    def setUp(self):
        self.entries = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))

    def test_every_transcript_entry_still_produces_its_recorded_output(self):
        results = replay(self.entries)
        if os.environ.get("UPDATE_DEMO_TRANSCRIPT"):
            for entry, (out, status) in zip(self.entries, results):
                entry["out"] = out
                entry["status"] = status
            TRANSCRIPT.write_text(json.dumps(self.entries, indent=2) + "\n", encoding="utf-8")
            self.skipTest("rewrote demo/transcript.json from a real run")
        for entry, (out, status) in zip(self.entries, results):
            with self.subTest(cmd=entry["cmd"]):
                self.assertEqual(
                    out, entry["out"],
                    f"{entry['cmd']}\n--- recorded ---\n{entry['out']}\n--- actual ---\n{out}")
                self.assertEqual(status, entry["status"], entry["cmd"])

    def test_transcript_holds_no_machine_paths(self):
        raw = TRANSCRIPT.read_text(encoding="utf-8")
        for marker in ("/Users/", "/var/folders", "/private/var", "/tmp/tmp"):
            self.assertNotIn(marker, raw)

    def test_every_picture_row_comes_from_the_transcript(self):
        rows = picture_rows()
        index = 0
        for entry in self.entries:
            if index >= len(rows):
                break  # the picture shows the first N rows only
            self.assertEqual(rows[index][0], "cmd", f"expected a prompt row for {entry['cmd']}")
            chunks = [rows[index][1].removeprefix("$")]
            index += 1
            while index < len(rows) and rows[index][0] == "cmd":
                chunks.append(rows[index][1].strip())
                index += 1
            # Wrapped command rows end in " \" and rejoin with one space.
            rebuilt = " ".join(c[:-2] if c.endswith(" \\") else c for c in chunks)
            self.assertEqual(rebuilt, entry["cmd"])

            for line in entry["out"].splitlines():
                if not line.strip():
                    continue
                if index >= len(rows) or rows[index][0] == "cmd":
                    break
                self.assertTrue(is_prefix(rows[index][1], line),
                                f"picture row {rows[index][1]!r} is not the start of {line!r}")
                index += 1
        self.assertGreater(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
