# TODO: known bugs and issues in `monitor.py`

Tracked but not yet fixed. The fixes applied so far are:

- Replaced blocking `time.sleep(0.5)` in the auto-tare path with `await asyncio.sleep(0.5)`.
- Switched the auto-tare zero check from `weight != 0` to a `0.2g` deadband (`abs(weight) > ZERO_DEADBAND_G`).
- `last_battery_check` is now advanced even when `scale.battery` returns `None` or raises a non-`AttributeError` exception, so we don't hammer the scale.
- The CSV file is now opened with a `with` block so it can't leak if header setup or anything in the loop raises.
- Added a TODO comment about the auto-tare-during-bird-present interaction (see below, item 1).

## Outstanding bugs

### 1. Auto-tare runs even while a bird is on the scale

`monitor.py`, auto-tare block in `monitor_scale`.

The check doesn't consider `bird_start_time`. If a bird is "present" and noise/movement pushes the weight momentarily outside `[min_bird_weight, max_bird_weight]`, we tare the scale and `continue`, so the `bird_left` event is never emitted with the right timestamp / duration. After the auto-tare the next reading sits near zero and eventually triggers `bird_left`, but with a wrong duration and a phantom `auto_tare` row in the CSV.

Fix sketch: gate the auto-tare on `bird_start_time is None`, e.g.

```python
if (
    bird_start_time is None
    and abs(weight) > ZERO_DEADBAND_G
    and (weight < min_bird_weight or weight > max_bird_weight)
):
    ...
```

There's already a `TODO:` comment in `monitor.py` next to the auto-tare block.

### 2. `bird_left` is never emitted when the bird "leaves" by going over `max_bird_weight`

`monitor.py`, in `monitor_scale`:

```python
elif bird_start_time is not None and weight < min_bird_weight:
```

Only a `weight < min_bird_weight` reading ends a visit. If `scale.weight` jumps from in-range to above `max_bird_weight` (e.g. a heavy object lands next to a bird, or the bird hops and lands hard), the auto-tare branch fires instead and (per bug #1) the visit silently disappears.

Fix sketch: end the visit on any out-of-range reading once we've also gated the auto-tare on `bird_start_time is None`:

```python
elif bird_start_time is not None and not (min_bird_weight <= weight <= max_bird_weight):
    ...
```

### 3. `input()` inside an async coroutine in `discover_acaia_scale`

`monitor.py`, `discover_acaia_scale`:

```python
choice = int(input("Select device number: ")) - 1
return acaia_devices[choice].address
```

Problems:

- `input()` is synchronous and blocks the asyncio event loop.
- `int(...)` crashes on any non-integer or empty input.
- No range check on `choice`: negative or out-of-bounds values either silently wrap (negative index) or raise `IndexError`.

Fix sketch: validate input in a loop, and either run the prompt via `loop.run_in_executor` or accept a `--device-index` CLI flag for non-interactive runs.

### 4. Default argument mismatch between `monitor_scale` and `main`

`monitor.py`:

```python
async def monitor_scale(scale, log_file, shutdown_event, ..., min_bird_weight=25, max_bird_weight=60, ...):
```

vs CLI:

```python
parser.add_argument("--min-weight", type=float, default=20.0, ...)
parser.add_argument("--max-weight", type=float, default=130.0, ...)
```

`main` always passes explicit values today, so behavior on the CLI path is correct, but anyone calling `monitor_scale` directly (e.g. a future test) will get a quietly different bird range. Pick one set of defaults and make them match, or drop the defaults from `monitor_scale` entirely.

### 5. SIGINT/SIGTERM handling is fragile

`monitor.py`, in `main`:

```python
shutdown_event = asyncio.Event()
loop = asyncio.get_running_loop()
loop.add_signal_handler(signal.SIGINT, shutdown_event.set)
```

- A second `Ctrl-C` just calls `shutdown_event.set()` again — there's no escape hatch if cleanup (e.g. `scale.disconnect()` over BLE) hangs.
- `SIGTERM` isn't handled, so running under systemd / Docker will hard-kill the process instead of letting it flush the current CSV row.

Fix sketch: also `loop.add_signal_handler(signal.SIGTERM, shutdown_event.set)`, and after the first signal, swap the handler so a second signal triggers a hard exit / cancels the monitor task.

### 6. Reconnect loop can spin forever

`monitor.py`, reconnect block in `monitor_scale`:

```python
while not shutdown_event.is_set():
    try:
        scale = await connect_scale(use_simulator, scenario, mac_address)
        ...
    except Exception as e:
        print(f"Reconnection failed: {e}. Retrying in {retry_delay}s...")
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, max_retry_delay)
```

No max-attempts or max-elapsed cap. If the scale is dead, the script sits here indefinitely with no telemetry beyond reconnect prints.

Fix sketch: log total elapsed reconnect time, and add an optional `--max-reconnect-seconds` (default e.g. one hour) that escalates to either exiting or paging via the email alert path.

## Minor / nice-to-have issues

- `weight = scale.weight or 0.0` (in `monitor_scale`) treats a legitimate `0.0` reading as falsy. Prefer `weight = scale.weight if scale.weight is not None else 0.0`.
- The device-name keyword list in `discover_acaia_scale` includes `"PR BT"` (with a space) and `"PROCH"`; `"PROCH"` likely already covers Proch devices, so `"PR BT"` is probably dead.
- In `main`, the line `print(f"  Battery alerts: {'disabled' if args.disable_battery_alerts else 'enabled'}")` sits inside `if alert_email and not args.disable_battery_alerts:`, so the `'disabled'` branch is unreachable.
- The inner `if not battery_monitoring_disabled:` inside the `except AttributeError:` is always true when reached (since we only enter the outer battery block when it's false). Safe to simplify.
- `csv_file.flush()` after every `bird_present` row will be I/O-heavy on slow disks. Consider flushing only on state transitions (`bird_landed`, `bird_left`, `auto_tare`).
- `connect_scale` is declared `async` but does only synchronous work; for real hardware `pyacaia`'s `connect()` is blocking and will stall the event loop during connection. Consider `loop.run_in_executor` for hardware connect/disconnect calls.
