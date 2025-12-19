#!/usr/bin/env python3
"""
Quick test of the simulator to verify different scenarios work correctly.
Run this to see what each scenario does before using them in monitor.py.
"""

import time

from simulator import create_mock_scale


def test_scenario(scenario_name, duration=15):
    """Test a specific scenario for a few seconds."""
    print(f"\n{'='*60}")
    print(f"Testing scenario: {scenario_name}")
    print(f"{'='*60}\n")

    scale = create_mock_scale(scenario=scenario_name)
    scale.connect()

    start_time = time.time()
    last_weight = None

    while time.time() - start_time < duration:
        weight = scale.weight

        # Only print when weight changes significantly
        if last_weight is None or abs(weight - last_weight) > 1:
            print(f"[{time.time() - start_time:6.1f}s] Weight: {weight:6.2f}g")
            last_weight = weight

        time.sleep(0.5)

    print(f"\nScenario '{scenario_name}' test complete\n")


if __name__ == "__main__":
    print("Simulator Test Suite")
    print("This will run each scenario for 15 seconds\n")

    scenarios = ["random", "quick_visits", "long_visit", "frequent_tare"]

    for scenario in scenarios:
        test_scenario(scenario, duration=15)

    print("\nAll tests complete!")
    print("\nTo use with monitor.py:")
    print("  uv run monitor --simulate --scenario <scenario_name>")
