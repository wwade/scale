"""Tests for pure helper functions in monitor.py.

We only exercise the parts that don't require BLE hardware or Gmail OAuth:

- XDG-aware state file path resolution
- MAC address load/save round-trip

The BLE and Gmail flows are covered (or stubbed out) elsewhere.
"""

from pathlib import Path

import pytest

import monitor


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point HOME and XDG_STATE_HOME at a clean tmp dir, then unset XDG so
    each test can opt back into setting it explicitly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return tmp_path


class TestStateFilePath:
    def test_uses_xdg_state_home_when_set(self, isolated_home, monkeypatch):
        xdg = isolated_home / "xdg-state"
        monkeypatch.setenv("XDG_STATE_HOME", str(xdg))

        path = monitor.get_state_file_path()

        assert path == xdg / "acaia-scale" / "mac_address.txt"
        assert path.parent.is_dir()

    def test_falls_back_to_home_local_state(self, isolated_home):
        path = monitor.get_state_file_path()

        assert path == isolated_home / ".local" / "state" / "acaia-scale" / "mac_address.txt"
        assert path.parent.is_dir()

    def test_creates_state_dir_idempotently(self, isolated_home, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(isolated_home / "xdg"))

        # Calling twice should not raise.
        first = monitor.get_state_file_path()
        second = monitor.get_state_file_path()

        assert first == second
        assert first.parent.is_dir()


class TestMacAddressRoundTrip:
    def test_load_returns_none_when_no_state_file(self, isolated_home, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(isolated_home / "xdg"))
        assert monitor.load_mac_address() is None

    def test_save_then_load_returns_value(self, isolated_home, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(isolated_home / "xdg"))

        monitor.save_mac_address("AA:BB:CC:DD:EE:FF")

        assert monitor.load_mac_address() == "AA:BB:CC:DD:EE:FF"

    def test_load_strips_whitespace(self, isolated_home, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(isolated_home / "xdg"))

        state_path = monitor.get_state_file_path()
        state_path.write_text("  11:22:33:44:55:66\n")

        assert monitor.load_mac_address() == "11:22:33:44:55:66"

    def test_save_overwrites_existing(self, isolated_home, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(isolated_home / "xdg"))

        monitor.save_mac_address("AA:AA:AA:AA:AA:AA")
        monitor.save_mac_address("BB:BB:BB:BB:BB:BB")

        assert monitor.load_mac_address() == "BB:BB:BB:BB:BB:BB"


class TestGmailCredentialsWhenAbsent:
    """`get_gmail_credentials` should return None (not raise) when neither
    credentials file exists. This is the only path safe to test in CI."""

    def test_returns_none_when_no_credentials_file(self, tmp_path, monkeypatch):
        # Pretend HOME is empty and CWD has no credentials.json.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        # Sanity: make sure the test's expected absence holds.
        assert not Path("credentials.json").exists()
        assert not (tmp_path / ".config" / "acaia-scale" / "credentials.json").exists()

        assert monitor.get_gmail_credentials() is None
