"""Hardware ADC abstractions and a mock ADC for testing."""
import time
import math
import random


class AdcDevice:
    """Base class for ADC devices."""

    def read_voltage(self, channel: int = 0) -> float:
        """Read a single voltage from the given channel in volts."""
        raise NotImplementedError()


class MockAdc(AdcDevice):
    """Mock ADC emitting a low-frequency sine wave plus small noise.
    
    Can simulate error conditions for testing error handling.
    """

    def __init__(self, amplitude: float = 1.5, offset: float = 1.5, freq: float = 0.25,
                 error_mode: str = "normal", error_rate: float = 0.0):
        """Initialize mock ADC.
        
        Args:
            amplitude: Sine wave amplitude (V)
            offset: DC offset (V)
            freq: Sine wave frequency (Hz)
            error_mode: "normal", "always_error", "random", or "stuck"
            error_rate: For random mode, probability of error (0.0-1.0)
        """
        self.amp = amplitude
        self.offset = offset
        self.freq = freq
        self.error_mode = error_mode.lower()
        self.error_rate = error_rate
        self._t0 = time.time()
        self._error_counter = 0

    def read_voltage(self, channel: int = 0) -> float:
        """Read voltage, possibly with simulated error."""
        # Check error conditions
        if self.error_mode == "always_error":
            self._error_counter += 1
            raise IOError(f"ADC Hardware Error (simulated) on channel {channel}")
        
        if self.error_mode == "random" and random.random() < self.error_rate:
            self._error_counter += 1
            raise IOError(f"ADC Communication Error (simulated, #{self._error_counter})")
        
        if self.error_mode == "stuck":
            # Return a stuck value
            return self.offset
        
        # Normal operation: sine wave + noise
        t = time.time() - self._t0
        return self.offset + self.amp * math.sin(2 * math.pi * self.freq * t) + (random.random() - 0.5) * 0.005
