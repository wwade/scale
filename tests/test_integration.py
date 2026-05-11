"""End-to-end test: drive `monitor.py --simulate` in a real subprocess
and verify it produces a well-formed CSV.

This catches regressions that escape unit tests:

- Broken argparse wiring (typos in flag names, missing pass-through).
- SIGINT / signal-handler setup failing at import time.
- The simulator CLI plumbing for `--seed` and `--max-events`.
- Top-level imports breaking under a fresh process.

The test deliberately uses the fast `test` scenario and a small
`--max-events` so it runs in a few seconds even with the auto-tare
back-off (`await asyncio.sleep(0.5)`).
"""

import csv
from pathlib import Path
import subprocess
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

VALID_EVENTS = {"auto_tare", "bird_landed", "bird_present", "bird_left"}


def _run_monitor(csv_path, *, max_events, seed=42, extra_args=()):
    """Run `monitor.py --simulate ...` and return the CompletedProcess."""
    cmd = [
        sys.executable,
        "monitor.py",
        "--simulate",
        "--scenario",
        "test",
        "--seed",
        str(seed),
        "--max-events",
        str(max_events),
        "--interval",
        "0.01",
        "--disable-battery-alerts",
        "--log-file",
        str(csv_path),
        *extra_args,
    ]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _read_rows(csv_path):
    with csv_path.open() as f:
        return list(csv.reader(f))


@pytest.fixture
def csv_path(tmp_path):
    return tmp_path / "out.csv"


def test_monitor_simulate_exits_cleanly_with_max_events(csv_path):
    result = _run_monitor(csv_path, max_events=5)

    assert result.returncode == 0, (
        f"monitor.py exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Reached --max-events=5" in result.stdout


def test_monitor_simulate_writes_well_formed_csv(csv_path):
    result = _run_monitor(csv_path, max_events=5)
    assert result.returncode == 0

    rows = _read_rows(csv_path)

    # Header + exactly max_events rows
    assert rows[0] == ["timestamp", "weight_g", "event", "battery_pct"]
    data = rows[1:]
    assert len(data) == 5

    # Every event label is one we know about, every weight is a parseable float.
    for row in data:
        _timestamp, weight, event, battery = row
        assert event in VALID_EVENTS, f"unexpected event: {event!r}"
        float(weight)
        # battery_pct is either empty or a float.
        if battery:
            float(battery)


def test_monitor_simulate_handles_argparse_errors(csv_path):
    """An unknown flag should make monitor.py exit non-zero with a
    descriptive message rather than crashing mid-loop."""
    result = subprocess.run(
        [sys.executable, "monitor.py", "--bogus-flag"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr
