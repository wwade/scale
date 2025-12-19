from enum import Enum
import random
import time


class BirdState(Enum):
    """Possible states of the simulated scale."""
    EMPTY = "empty"
    BIRD_PRESENT = "bird_present"
    JUNK = "junk"  # Something too light or too heavy


class MockAcaiaScale:
    """Mock Acaia scale for testing without hardware."""

    def __init__(self, mac=None, scenario="random"):
        """
        Initialize mock scale.

        Args:
            mac: Ignored for mock
            scenario: Testing scenario to simulate
                - "random": Random bird visits with occasional junk
                - "quick_visits": Many quick bird visits
                - "long_visit": One long bird sitting session
                - "frequent_tare": Lots of junk requiring tares
        """
        self.mac = mac
        self.scenario = scenario
        self.connected = False
        self._weight = 0.0
        self._tare_offset = 0.0
        self._state = BirdState.EMPTY
        self._state_start_time = time.time()
        self._bird_weight = None
        self._battery_level = 100.0  # Start at 100%
        self._battery_start_time = time.time()

        # Bird weight parameters (typical small bird range)
        self.min_bird_weight = 25
        self.max_bird_weight = 55

        # Timing parameters based on scenario
        if scenario == "quick_visits":
            self.visit_duration_range = (2, 8)  # 2-8 seconds
            self.empty_duration_range = (3, 10)  # 3-10 seconds between visits
            self.junk_probability = 0.1
        elif scenario == "long_visit":
            self.visit_duration_range = (30, 60)  # 30-60 seconds
            self.empty_duration_range = (15, 30)
            self.junk_probability = 0.05
        elif scenario == "frequent_tare":
            self.visit_duration_range = (3, 10)
            self.empty_duration_range = (2, 5)
            self.junk_probability = 0.5  # 50% chance of junk
        else:  # random
            self.visit_duration_range = (5, 20)  # 5-20 seconds
            self.empty_duration_range = (10, 30)  # 10-30 seconds between visits
            self.junk_probability = 0.2

    def connect(self):
        """Simulate connection to scale."""
        self.connected = True
        print(f"[SIMULATOR] Connected to mock scale (scenario: {self.scenario})")

    def disconnect(self):
        """Simulate disconnection from scale."""
        self.connected = False
        print("[SIMULATOR] Disconnected from mock scale")

    def tare(self):
        """Tare the scale (zero it)."""
        self._tare_offset = self._weight
        print(f"[SIMULATOR] Tared scale (offset: {self._tare_offset:.1f}g)")

    @property
    def weight(self):
        """Get current weight, updating state as needed."""
        self._update_state()

        # Return weight minus tare offset
        raw_weight = self._weight - self._tare_offset

        # Add small random noise to make it realistic
        noise = random.uniform(-0.5, 0.5)
        return raw_weight + noise

    @property
    def battery(self):
        """Get current battery level (simulated drain over time)."""
        # Simulate battery drain: -0.1% per minute
        elapsed_minutes = (time.time() - self._battery_start_time) / 60.0
        self._battery_level = max(0.0, 100.0 - (elapsed_minutes * 0.1))
        return self._battery_level

    def _update_state(self):
        """Update the simulated state based on elapsed time."""
        elapsed = time.time() - self._state_start_time

        if self._state == BirdState.EMPTY:
            # Check if it's time for something to appear
            min_duration, max_duration = self.empty_duration_range
            if elapsed > random.uniform(min_duration, max_duration):
                # Decide what appears: bird or junk
                if random.random() < self.junk_probability:
                    self._transition_to_junk()
                else:
                    self._transition_to_bird()

        elif self._state == BirdState.BIRD_PRESENT:
            # Check if bird should leave
            min_duration, max_duration = self.visit_duration_range
            if elapsed > random.uniform(min_duration, max_duration):
                self._transition_to_empty()

        elif self._state == BirdState.JUNK:
            # Junk stays for a short random time
            if elapsed > random.uniform(2, 6):
                self._transition_to_empty()

    def _transition_to_bird(self):
        """Transition to bird present state."""
        self._state = BirdState.BIRD_PRESENT
        self._state_start_time = time.time()
        # Generate a random bird weight and stick with it for this visit
        self._bird_weight = random.uniform(self.min_bird_weight, self.max_bird_weight)
        self._weight = self._bird_weight
        print(f"[SIMULATOR] Bird landed ({self._bird_weight:.1f}g)")

    def _transition_to_empty(self):
        """Transition to empty state."""
        self._state = BirdState.EMPTY
        self._state_start_time = time.time()
        self._weight = 0
        self._bird_weight = None
        print("[SIMULATOR] Scale empty")

    def _transition_to_junk(self):
        """Transition to junk state (something requiring tare)."""
        self._state = BirdState.JUNK
        self._state_start_time = time.time()

        # Generate either too-light, too-heavy, or negative junk
        rand = random.random()
        if rand < 0.33:
            # Light junk (dust, small debris)
            self._weight = random.uniform(0.5, 15)
            print(f"[SIMULATOR] Light junk on scale ({self._weight:.1f}g)")
        elif rand < 0.66:
            # Heavy junk (cup, bowl, hand, etc.)
            self._weight = random.uniform(70, 200)
            print(f"[SIMULATOR] Heavy junk on scale ({self._weight:.1f}g)")
        else:
            # Negative weight (something removed or scale drift)
            self._weight = random.uniform(-20, -2)
            print(f"[SIMULATOR] Negative weight on scale ({self._weight:.1f}g)")


def create_mock_scale(mac=None, scenario="random"):
    """
    Factory function to create a mock scale.

    Args:
        mac: MAC address (ignored for mock)
        scenario: Testing scenario ("random", "quick_visits", "long_visit", "frequent_tare")

    Returns:
        MockAcaiaScale instance
    """
    return MockAcaiaScale(mac=mac, scenario=scenario)
