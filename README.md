# Project Overview

This is a Python project for monitoring Acaia coffee scales over Bluetooth LE. The main workflow is continuous bird-weight logging with optional battery monitoring and Gmail-based low-battery alerts.

The project uses:

- `pyacaia` for scale communication
- `bleak` for Bluetooth device discovery
- Gmail API OAuth credentials for optional battery alert emails

# Development Environment

This project uses `uv` for dependency management and command execution. Prefer running all commands through `uv`.

```bash
# Discover nearby Acaia devices
uv run python discover.py

# Monitor a real scale and write bird_weights.csv
uv run monitor
uv run monitor --interval 1.5 --max-weight 130  # Writes to bird_weights.csv

# Run the simulator instead of real BLE hardware
uv run monitor --simulate

# Exercise the simulator scenarios directly
uv run python test_simulator.py

# Lint and format
uv run ruff check .
uv run ruff format .
```

# Key Files

- `monitor.py` - Main monitoring CLI, auto-tare logic, CSV logging, battery checks, Gmail alerts
- `discover.py` - BLE discovery script for nearby Acaia-like devices
- `simulator.py` - Mock scale implementation for hardware-free development
- `test_simulator.py` - Quick manual test runner for simulator scenarios
- `pyproject.toml` - Project metadata, dependencies, and Ruff configuration

# Working With Acaia Scales

The scale must be powered on and within Bluetooth range. Likely Acaia devices advertise with names like:

- `PROCHBT001`
- `PR BT CB0E`
- names containing `ACAIA`, `PYXIS`, `LUNAR`, or `PEARL`

On first successful discovery, the selected MAC address is cached in:

- `$XDG_STATE_HOME/acaia-scale/mac_address.txt`, or
- `~/.local/state/acaia-scale/mac_address.txt`

Use `--discover` to force rediscovery.

# Monitoring Features

`monitor.py` supports:

- Auto-tare when the current reading is non-zero but outside the configured bird-weight range
- Bird event detection for landing, presence, and departure
- Continuous CSV logging with columns: `timestamp`, `weight_g`, `event`, `battery_pct`
- Periodic battery checks through the connected scale
- Optional low-battery email alerts via Gmail OAuth
- Automatic reconnect attempts if the scale disconnects

Common options:

```bash
uv run monitor --interval 1.0 --min-weight 20 --max-weight 60
uv run monitor --discover
uv run monitor --battery-threshold 15 --alert-email you@example.com
uv run monitor --disable-battery-alerts
```

# Gmail Battery Alerts

Battery alerts are optional. If `--alert-email` is provided, or `ALERT_EMAIL` is set, the monitor will try to send a low-battery alert using Gmail API credentials.

Credential lookup order:

- `./credentials.json`
- `~/.config/acaia-scale/credentials.json`

OAuth tokens are stored next to the chosen credentials file as `token.json`.

If credentials are unavailable, the monitor explains the setup requirements at startup and exits unless battery alerts are disabled.

# Testing Without Hardware

Use `--simulate` to run without a real scale:

```bash
uv run monitor --simulate
uv run monitor --simulate --scenario quick_visits
uv run monitor --simulate --scenario long_visit
uv run monitor --simulate --scenario frequent_tare
uv run python test_simulator.py
```

Available simulator scenarios:

- `random` - Random bird visits with occasional junk
- `quick_visits` - Frequent short visits
- `long_visit` - Longer sitting sessions
- `frequent_tare` - Frequent junk events that trigger tare behavior
