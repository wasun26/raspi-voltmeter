"""Shared scan gain control; called only by the acquisition owner thread."""
import math
import json
import time
from queue import SimpleQueue


GAINS = (1, 2, 4, 8, 16, 32, 64)


class GainConfigurationError(RuntimeError):
    pass


class ScanReadings(dict):
    """Voltage mapping with immutable capture-time metadata for storage retries."""

    def __init__(self, *args, metadata=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata = metadata or {}


class AutoGain:
    def __init__(self, enabled=False, min_gain=1, max_gain=64,
                 high_fraction=0.8, low_fraction=0.2, quiet_seconds=10,
                 cooldown_seconds=3):
        if min_gain not in GAINS or max_gain not in GAINS or min_gain > max_gain:
            raise ValueError("Auto gain limits must be supported gains in ascending order")
        if not 0 < low_fraction < high_fraction < 1:
            raise ValueError("Auto gain thresholds must satisfy 0 < low < high < 1")
        if (not math.isfinite(quiet_seconds) or not math.isfinite(cooldown_seconds)
                or quiet_seconds <= 0 or cooldown_seconds < 0):
            raise ValueError("Auto gain timing must be finite and nonnegative (quiet > 0)")
        self.enabled = bool(enabled)
        self.gains = tuple(g for g in GAINS if min_gain <= g <= max_gain)
        self.high = high_fraction
        self.low = low_fraction
        self.quiet_seconds = quiet_seconds
        self.cooldown_seconds = cooldown_seconds
        self.pending = self.gains[0] if enabled else None
        self.reason = "auto_start" if enabled else ""
        self.low_since = None
        self.last_change = None
        self.last_scan = None
        self.requests = SimpleQueue()

    def request_mode(self, gain):
        # The UI queues intent; no hardware access occurs here.
        if gain is not None and gain not in GAINS:
            raise ValueError("Unsupported manual gain")
        self.requests.put(gain)

    def reset_quiet(self):
        self.low_since = None
        self.last_scan = None
        # A pause must not apply a previously scheduled quiet-time increase.
        if self.reason == "quiet_increase":
            self.pending = None

    def begin_scan(self, adc, now):
        while not self.requests.empty():
            gain = self.requests.get_nowait()
            self.enabled = gain is None
            self.pending = self.gains[0] if self.enabled else gain
            self.reason = "auto_start" if self.enabled else "manual"
            self.low_since = None
        event = ""
        duration = 0.0
        if self.pending is not None:
            target = self.pending
            event = self.reason
            if target != adc.gain:
                before = time.monotonic()
                try:
                    adc.set_gain(target)
                except Exception as exc:
                    raise GainConfigurationError(f"Gain change failed; measurement stopped: {exc}") from exc
                duration = time.monotonic() - before
                event = self.reason
            self.pending = None
            self.last_change = now
            self.low_since = None
        return event, duration

    def observe(self, gain, peak, saturated, now):
        if not self.enabled:
            return
        if self.last_scan is not None and now - self.last_scan > self.quiet_seconds:
            self.low_since = None  # No quiet-time credit during storage outages/pauses.
        self.last_scan = now
        index = self.gains.index(gain)
        if peak >= self.high:
            self.low_since = None
            if index:
                # A clipped conversion cannot tell us its true amplitude.
                self.pending = self.gains[0] if saturated else self.gains[index - 1]
                self.reason = "clipped_reduce" if saturated else "headroom_reduce"
            return
        if peak >= self.low or index == len(self.gains) - 1:
            self.low_since = None
            return
        if self.low_since is None:
            self.low_since = now
        if (now - self.low_since >= self.quiet_seconds
                and (self.last_change is None or now - self.last_change >= self.cooldown_seconds)):
            self.pending = self.gains[index + 1]
            self.reason = "quiet_increase"
            self.low_since = None


def read_scan(adc, channels, averaging, controller):
    """All channels share one gain; every actual conversion is checked before averaging."""
    event, duration = controller.begin_scan(adc, time.monotonic())
    gain = adc.gain
    vref = adc.vref
    full_scale = vref / gain * (1 if adc.single_ended else 2)
    readings = ScanReadings(metadata={
        "gain": gain, "vref_V": vref, "gain_mode": "auto" if controller.enabled else "manual",
        "gain_event": event, "gain_change_s": duration,
        "input_mode": "single-ended" if adc.single_ended else "differential",
        "averaging": averaging,
        "adc_data_rate_SPS": getattr(adc, "data_rate", getattr(adc, "sample_rate", "")),
        "channels": {},
    })
    scan_peak = 0.0
    scan_clipped = False
    for channel in channels:
        values, raw_values, timestamps = [], [], []
        for _ in range(averaging):
            voltage = adc.read_voltage(channel)
            if not math.isfinite(voltage):
                raise ValueError("ADC returned a non-finite voltage")
            timestamps.append(time.time())
            values.append(voltage)
            raw_values.append(getattr(adc, "last_raw", round(voltage / full_scale * 0x7FFFFF)))
        peak = max(abs(raw) / 0x7FFFFF for raw in raw_values)
        clipped = any(raw >= 0x7FFFFF or raw <= -0x800000 for raw in raw_values)
        # Mock uses symmetric signed endpoints.
        if type(adc).__name__ == "MockAdc":
            clipped = clipped or min(raw_values) <= -0x7FFFFF
        readings[channel] = sum(values) / averaging
        readings.metadata["channels"][channel] = {
            "conversion_start_unix_s": timestamps[0], "conversion_end_unix_s": timestamps[-1],
            "raw_count": raw_values[-1], "raw_min": min(raw_values), "raw_max": max(raw_values),
            "peak_fraction": peak, "clipped": int(clipped),
            "raw_counts": json.dumps(raw_values),
            "conversion_unix_s": json.dumps(timestamps),
        }
        scan_peak = max(scan_peak, peak)
        scan_clipped |= clipped
    readings.metadata["clipped"] = int(scan_clipped)
    readings.metadata["peak_fraction"] = scan_peak
    controller.observe(gain, scan_peak, scan_clipped, time.monotonic())
    return readings
