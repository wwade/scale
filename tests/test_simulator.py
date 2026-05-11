"""Tests for the MockAcaiaScale simulator.

These tests drive the simulator's state machine deterministically by seeding
`random` and by setting `_state_start_time` / `_battery_start_time` directly,
so they run in well under a second and don't depend on wall-clock time.
"""

import random
import time

import pytest

from simulator import BirdState, MockAcaiaScale, create_mock_scale


@pytest.fixture(autouse=True)
def _seed_random():
    """Make every test deterministic."""
    random.seed(42)


class TestConnectionLifecycle:
    def test_starts_disconnected(self):
        scale = MockAcaiaScale()
        assert scale.connected is False

    def test_connect_marks_connected(self):
        scale = MockAcaiaScale()
        scale.connect()
        assert scale.connected is True

    def test_disconnect_marks_disconnected(self):
        scale = MockAcaiaScale()
        scale.connect()
        scale.disconnect()
        assert scale.connected is False


class TestTare:
    def test_tare_zeros_current_weight(self):
        scale = MockAcaiaScale()
        scale._weight = 75.0
        scale._state = BirdState.JUNK  # prevent _update_state from clobbering
        scale._state_start_time = time.time()

        scale.tare()

        # Weight property adds +/-0.5g of noise, so allow a small tolerance.
        assert abs(scale.weight) < 1.0

    def test_tare_offset_carries_forward(self):
        scale = MockAcaiaScale()
        scale._weight = 30.0
        scale._state = BirdState.BIRD_PRESENT
        scale._state_start_time = time.time()

        scale.tare()
        # Bump the underlying weight; the offset should still be applied.
        scale._weight = 50.0

        # Effective weight = 50 - 30 = 20g, plus noise.
        assert 18.5 < scale.weight < 21.5


class TestBattery:
    def test_battery_starts_at_full(self):
        scale = MockAcaiaScale()
        # Start fresh — no elapsed time yet.
        scale._battery_start_time = time.time()
        assert scale.battery == pytest.approx(100.0, abs=0.01)

    def test_battery_decays_monotonically(self):
        scale = MockAcaiaScale()
        # Pretend 60 minutes have passed -> 0.1%/min * 60 = 6%.
        scale._battery_start_time = time.time() - 60 * 60
        assert scale.battery == pytest.approx(94.0, abs=0.5)

    def test_battery_clamped_at_zero(self):
        scale = MockAcaiaScale()
        # Pretend 10 years have passed; battery shouldn't go negative.
        scale._battery_start_time = time.time() - 10 * 365 * 24 * 3600
        assert scale.battery == 0.0


class TestStateTransitions:
    def test_bird_transition_produces_in_range_weight(self):
        scale = MockAcaiaScale()
        scale._transition_to_bird()

        assert scale._state == BirdState.BIRD_PRESENT
        assert scale.min_bird_weight <= scale._bird_weight <= scale.max_bird_weight
        # Reported weight (with noise) should be near the bird weight.
        assert abs(scale.weight - scale._bird_weight) < 1.0

    @pytest.mark.parametrize(
        "forced_rand, expected_category",
        [
            (0.1, "light"),  # rand < 0.33
            (0.5, "heavy"),  # 0.33 <= rand < 0.66
            (0.9, "negative"),  # rand >= 0.66
        ],
    )
    def test_junk_transition_produces_out_of_range_weight(
        self, monkeypatch, forced_rand, expected_category
    ):
        scale = MockAcaiaScale()
        # Force the branch inside _transition_to_junk by pinning random.random()
        # for the first call (the branch selector). Subsequent random.uniform()
        # calls inside the branch use their own RNG path and stay seeded.
        calls = {"n": 0}
        real_random = random.random

        def fake_random():
            calls["n"] += 1
            if calls["n"] == 1:
                return forced_rand
            return real_random()

        monkeypatch.setattr("simulator.random.random", fake_random)
        scale._transition_to_junk()

        w = scale._weight
        assert scale._state == BirdState.JUNK
        # Junk is never in the bird range.
        assert not (scale.min_bird_weight <= w <= scale.max_bird_weight)

        if expected_category == "light":
            assert 0 < w < scale.min_bird_weight
        elif expected_category == "heavy":
            assert w > scale.max_bird_weight
        else:
            assert w < 0

    def test_empty_transition_clears_weight(self):
        scale = MockAcaiaScale()
        scale._transition_to_bird()
        assert scale._weight > 0

        scale._transition_to_empty()
        assert scale._state == BirdState.EMPTY
        assert scale._weight == 0
        assert scale._bird_weight is None

    def test_update_state_promotes_empty_to_bird_or_junk(self):
        scale = MockAcaiaScale(scenario="quick_visits")
        assert scale._state == BirdState.EMPTY
        # Force "enough" elapsed time so _update_state must transition.
        scale._state_start_time = time.time() - 1000

        scale._update_state()
        assert scale._state in {BirdState.BIRD_PRESENT, BirdState.JUNK}

    def test_update_state_returns_bird_to_empty(self):
        scale = MockAcaiaScale()
        scale._transition_to_bird()
        scale._state_start_time = time.time() - 1000

        scale._update_state()
        assert scale._state == BirdState.EMPTY


class TestScenarios:
    @pytest.mark.parametrize(
        "scenario",
        ["random", "quick_visits", "long_visit", "frequent_tare"],
    )
    def test_scenarios_have_valid_parameters(self, scenario):
        scale = create_mock_scale(scenario=scenario)

        min_visit, max_visit = scale.visit_duration_range
        min_empty, max_empty = scale.empty_duration_range

        assert 0 < min_visit < max_visit
        assert 0 < min_empty < max_empty
        assert 0.0 <= scale.junk_probability <= 1.0

    def test_frequent_tare_has_higher_junk_probability_than_random(self):
        random_scale = create_mock_scale(scenario="random")
        frequent_scale = create_mock_scale(scenario="frequent_tare")
        assert frequent_scale.junk_probability > random_scale.junk_probability

    def test_long_visit_has_longer_visits_than_quick_visits(self):
        long_scale = create_mock_scale(scenario="long_visit")
        quick_scale = create_mock_scale(scenario="quick_visits")
        assert long_scale.visit_duration_range[0] >= quick_scale.visit_duration_range[1]


class TestFactory:
    def test_create_mock_scale_returns_instance(self):
        scale = create_mock_scale()
        assert isinstance(scale, MockAcaiaScale)
        assert scale.scenario == "random"

    def test_create_mock_scale_respects_scenario(self):
        scale = create_mock_scale(scenario="long_visit")
        assert scale.scenario == "long_visit"
