"""Tests for the bird_interval feature: faster polling while a bird is on the scale."""

import asyncio
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from monitor import monitor_scale

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Keep subprocess runs fast without overriding --bird-interval under test.
_FAST_INTERVAL = ("--interval", "0.01")


class QueuedWeightScale:
    """Minimal scale stub with a deterministic weight sequence."""

    def __init__(self, weights):
        self._weights = list(weights)
        self.connected = True
        self.battery = 100.0

    @property
    def weight(self):
        if self._weights:
            return self._weights.pop(0)
        return 0.0

    def tare(self):
        pass

    def disconnect(self):
        self.connected = False


async def _run_monitor_with_captured_sleeps(
    scale,
    csv_path,
    *,
    interval,
    bird_interval,
    max_events=None,
    stop_after_sleeps=None,
):
    """Run monitor_scale and record every asyncio.sleep duration."""
    shutdown = asyncio.Event()
    sleeps = []
    original_sleep = asyncio.sleep

    async def capture_sleep(duration):
        sleeps.append(duration)
        if stop_after_sleeps is not None and len(sleeps) >= stop_after_sleeps:
            shutdown.set()
        await original_sleep(0)

    with patch("monitor.asyncio.sleep", side_effect=capture_sleep):
        await monitor_scale(
            scale,
            str(csv_path),
            shutdown,
            interval=interval,
            bird_interval=bird_interval,
            max_events=max_events,
            battery_check_interval=999999,
        )

    return sleeps


class TestBirdIntervalSleep:
    """Unit tests: verify which interval is passed to asyncio.sleep."""

    def test_sleep_uses_bird_interval_during_visit(self, tmp_path):
        # Three in-range readings: landed, then present samples.
        scale = QueuedWeightScale([40.0, 45.0, 50.0])
        csv_path = tmp_path / "out.csv"

        sleeps = asyncio.run(
            _run_monitor_with_captured_sleeps(
                scale,
                csv_path,
                interval=5.0,
                bird_interval=0.25,
                max_events=3,
            )
        )

        assert 0.25 in sleeps
        assert 5.0 not in sleeps

    def test_sleep_uses_normal_interval_when_idle(self, tmp_path):
        scale = QueuedWeightScale([0.0] * 10)
        csv_path = tmp_path / "out.csv"

        sleeps = asyncio.run(
            _run_monitor_with_captured_sleeps(
                scale,
                csv_path,
                interval=5.0,
                bird_interval=0.25,
                stop_after_sleeps=2,
            )
        )

        assert sleeps == [5.0, 5.0]

    def test_sleep_reverts_to_interval_after_bird_left(self, tmp_path):
        scale = QueuedWeightScale([40.0, 0.0])
        csv_path = tmp_path / "out.csv"

        sleeps = asyncio.run(
            _run_monitor_with_captured_sleeps(
                scale,
                csv_path,
                interval=5.0,
                bird_interval=0.25,
                stop_after_sleeps=2,
            )
        )

        assert sleeps == [0.25, 5.0]

    def test_auto_tare_uses_settle_sleep_not_bird_interval(self, tmp_path):
        # Out-of-range triggers auto_tare (0.5s settle), then idle uses interval.
        scale = QueuedWeightScale([100.0, 0.0])
        csv_path = tmp_path / "out.csv"

        sleeps = asyncio.run(
            _run_monitor_with_captured_sleeps(
                scale,
                csv_path,
                interval=5.0,
                bird_interval=0.25,
                stop_after_sleeps=2,
            )
        )

        assert sleeps[0] == 0.5
        assert sleeps[1] == 5.0


def _run_monitor_subprocess(csv_path, *, max_events, extra_args=()):
    cmd = [
        sys.executable,
        "monitor.py",
        "--simulate",
        "--scenario",
        "test",
        "--seed",
        "42",
        "--max-events",
        str(max_events),
        "--disable-battery-alerts",
        "--log-file",
        str(csv_path),
        *_FAST_INTERVAL,
        *extra_args,
    ]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


class TestBirdIntervalCLI:
    """Integration: --bird-interval flag threads through argparse to monitor_scale."""

    def test_bird_interval_flag_in_settings_output(self, tmp_path):
        csv_path = tmp_path / "out.csv"
        result = _run_monitor_subprocess(
            csv_path,
            max_events=2,
            extra_args=["--bird-interval", "0.25"],
        )

        assert result.returncode == 0, (
            f"monitor.py exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "Reached --max-events=2" in result.stdout
        assert "Bird polling interval: 0.25s" in result.stdout

    def test_bird_interval_defaults_in_settings_output(self, tmp_path):
        csv_path = tmp_path / "out.csv"
        result = _run_monitor_subprocess(csv_path, max_events=1)

        assert result.returncode == 0
        assert "Bird polling interval: 0.5s" in result.stdout
