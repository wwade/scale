# Project Overview

This is a Python project for connecting to and communicating with Acaia coffee scales via Bluetooth LE. The primary use case is monitoring and logging bird weights continuously. It uses the `pyacaia` library for scale communication and `bleak` for Bluetooth device discovery.

# Development Environment

This project uses uv for dependency management. All commands should be run through uv:

```bash
# Quick test connection
uv run python main.py

# Discover Acaia scales
uv run python discover.py

# Monitor scale and log bird weights
uv run monitor
uv run monitor --interval 1.5 --max-weight 130  # Writes to bird_weights.csv

# Add dependencies
uv add <package>
```

# Key Files

- `monitor.py` - Primary script for continuous bird weight monitoring with auto-tare and CSV logging
- `simulator.py` - Mock Acaia scale for testing without hardware
- `test_simulator.py` - Test script to verify simulator scenarios
- `main.py` - Simple test script that connects to the scale and reads a single weight value
- `discover.py` - Bluetooth discovery script to find Acaia devices and their MAC addresses
- `pyproject.toml` - uv/hatchling configuration with dependencies (pyacaia, bleak)

# Working with Acaia Scales

The Acaia scale must be powered on and within Bluetooth range. Acaia devices advertise with Bluetooth names like:
- `PROCHBT001` (common for Acaia Pearl)
- `PR BT CB0E`
- Or names containing: ACAIA, PYXIS, LUNAR, PEARL

MAC addresses are automatically discovered on first run and cached in `$XDG_STATE_HOME/acaia-scale/mac_address.txt` (or `~/.local/state/acaia-scale/mac_address.txt`). Use `--discover` flag to force rediscovery.

# Bird Monitoring Features

The `monitor.py` script includes:
- **Auto-tare**: Automatically tares the scale when weight is non-zero but outside bird range (< 20g or > 60g)
- **Event detection**: Logs when birds land and leave, with timestamps
- **Continuous logging**: Records all weight readings while bird is present (20-60g range by default)
- **CSV output**: Logs to CSV with columns: timestamp, weight_g, event (bird_landed, bird_present, bird_left)

# Testing Without Hardware

Use the `--simulate` flag to test without an actual Acaia scale:

```bash
# Test with random bird visits
uv run monitor --simulate

# Test specific scenarios
uv run monitor --simulate --scenario quick_visits
uv run monitor --simulate --scenario long_visit
uv run monitor --simulate --scenario frequent_tare

# Quick test of all scenarios
uv run python test_simulator.py
```

Available scenarios:
- `random`: Random bird visits with occasional junk (default)
- `quick_visits`: Frequent short visits (2-8 seconds)
- `long_visit`: Longer sitting sessions (30-60 seconds)
- `frequent_tare`: Lots of junk requiring auto-tare (50% of events)
