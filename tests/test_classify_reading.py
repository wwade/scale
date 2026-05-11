"""Tests for `classify_reading`, the pure bird/auto-tare classifier.

These tests pin the **current** behavior of the classifier, which is a
literal extraction of the existing `monitor_scale` branching. That
includes the two known quirks tracked in `TODO_BUGS.md`:

1. Auto-tare fires regardless of whether a bird is present. A noisy
   reading that briefly leaves the bird range while a bird is on the
   scale will tare under the bird.
2. Only `weight < min_bird_weight` ends a visit. A reading that jumps
   above `max_bird_weight` while a bird is present hits the
   (unconditional) auto-tare branch instead.

Fixing those is intentionally out of scope for this refactor — see the
"Out of scope" section of `new_plan.md`. Each fix should land in its
own behavior-change PR with its own assertions, at which point these
tests update deliberately rather than the state machine drifting under
us by accident.
"""

import pytest

from monitor import (
    EVENT_AUTO_TARE,
    EVENT_BIRD_LANDED,
    EVENT_BIRD_LEFT,
    EVENT_BIRD_PRESENT,
    EVENT_IDLE,
    classify_reading,
)

MIN_W = 25.0
MAX_W = 60.0


def _classify(weight, bird_present=False, zero_deadband=0.2):
    return classify_reading(
        weight,
        bird_present=bird_present,
        min_bird_weight=MIN_W,
        max_bird_weight=MAX_W,
        zero_deadband=zero_deadband,
    )


class TestNoBirdPresent:
    @pytest.mark.parametrize("weight", [0.0, 0.1, -0.1, 0.2, -0.2])
    def test_within_deadband_is_idle(self, weight):
        assert _classify(weight) == EVENT_IDLE

    @pytest.mark.parametrize("weight", [25.0, 40.0, 60.0, 59.9])
    def test_in_range_starts_visit(self, weight):
        assert _classify(weight) == EVENT_BIRD_LANDED

    @pytest.mark.parametrize("weight", [0.3, 5.0, 24.9, 60.1, 150.0, -5.0, -100.0])
    def test_out_of_range_outside_deadband_triggers_auto_tare(self, weight):
        assert _classify(weight) == EVENT_AUTO_TARE


class TestBirdPresent:
    @pytest.mark.parametrize("weight", [25.0, 40.0, 60.0, 47.3])
    def test_in_range_keeps_visit(self, weight):
        assert _classify(weight, bird_present=True) == EVENT_BIRD_PRESENT

    @pytest.mark.parametrize("weight", [0.0, 0.1, -0.1, 0.2, -0.2])
    def test_within_deadband_ends_visit(self, weight):
        # Inside the deadband the auto-tare branch can't fire, so the
        # `weight < min_bird_weight` branch closes the visit.
        assert _classify(weight, bird_present=True) == EVENT_BIRD_LEFT

    @pytest.mark.parametrize("weight", [0.3, 5.0, 24.9, -5.0, -100.0])
    def test_light_out_of_range_auto_tares_under_bird(self, weight):
        # TODO_BUGS item 1: auto-tare currently runs even while a bird
        # is on the scale, so a noisy "light" reading tares the scale
        # under the bird instead of emitting `bird_left`.
        assert _classify(weight, bird_present=True) == EVENT_AUTO_TARE

    @pytest.mark.parametrize("weight", [60.1, 150.0, 200.0])
    def test_heavy_out_of_range_auto_tares_under_bird(self, weight):
        # TODO_BUGS item 2 (combined with item 1): a reading above
        # max_bird_weight while a bird is present takes the auto-tare
        # branch rather than ending the visit.
        assert _classify(weight, bird_present=True) == EVENT_AUTO_TARE


class TestBoundaryInclusion:
    """The bird range is closed on both ends: min and max are valid."""

    def test_min_is_in_range(self):
        assert _classify(MIN_W) == EVENT_BIRD_LANDED
        assert _classify(MIN_W, bird_present=True) == EVENT_BIRD_PRESENT

    def test_max_is_in_range(self):
        assert _classify(MAX_W) == EVENT_BIRD_LANDED
        assert _classify(MAX_W, bird_present=True) == EVENT_BIRD_PRESENT

    def test_just_below_min_no_bird_is_auto_tare(self):
        assert _classify(MIN_W - 0.01) == EVENT_AUTO_TARE

    def test_just_above_max_no_bird_is_auto_tare(self):
        assert _classify(MAX_W + 0.01) == EVENT_AUTO_TARE


class TestCustomDeadband:
    def test_wider_deadband_swallows_more_idle(self):
        # 0.4g sits inside a 0.5g deadband -> idle.
        assert _classify(0.4, zero_deadband=0.5) == EVENT_IDLE
        # ... but outside the default deadband -> auto_tare.
        assert _classify(0.4) == EVENT_AUTO_TARE

    def test_wider_deadband_suppresses_under_bird_auto_tare(self):
        # With a wide enough deadband to swallow the reading, the
        # auto-tare branch is skipped and the visit ends normally.
        assert _classify(5.0, bird_present=True, zero_deadband=10.0) == EVENT_BIRD_LEFT
