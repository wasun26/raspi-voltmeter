"""Acquisition manager: reads ADC periodically and delivers samples to callbacks."""
import threading
import time
from typing import Callable, List
from core.auto_gain import AutoGain, GainConfigurationError, read_scan


class AcquisitionManager:
    """Simple acquisition manager that polls an AdcDevice in a background thread."""

    def __init__(self, adc_device, channels: List[int] = [0], sample_rate: float = 10.0, averaging: int = 1, recorder=None, auto_gain=None):
        self.adc = adc_device
        self.channels = list(channels)
        self.sample_rate = float(sample_rate)
        self.averaging = int(averaging)
        self.recorder = recorder
        self.auto_gain = AutoGain(**(auto_gain or {}))
        self.last_scan_metadata = {}
        self.clipped_scan_count = 0
        self._settings_lock = threading.Lock()
        self._requested_rate = None
        self.recording_error = None
        self.recording_retrying = False
        self.pending_recording = None
        self._stop_event = threading.Event()

        self._callbacks: List[Callable] = []
        self._running = False
        self._thread = None
        self._error_count = 0

    def add_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def remove_callback(self, fn: Callable):
        if fn in self._callbacks:
            self._callbacks.remove(fn)

    def start(self):
        if self.recording_error is not None and not self.recording_retrying:
            raise RuntimeError("Recording failed; restart after fixing storage") from self.recording_error
        if self._running:
            return
        self._stop_event.clear()
        self.auto_gain.reset_quiet()
        self._running = True
        self.set_sample_rate(self.sample_rate)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
        if self.recording_retrying:
            self.recording_retrying = False
            self.recording_error = None

    def set_sample_rate(self, rate_hz: float):
        self.sample_rate = float(rate_hz)
        if self._running:
            with self._settings_lock:
                self._requested_rate = self.sample_rate
        elif hasattr(self.adc, "set_sample_rate"):
            self.adc.set_sample_rate(self.sample_rate)

    def _run(self):
        while self._running:
            period = 1.0 / self.sample_rate if self.sample_rate > 0 else 0.1
            started = time.monotonic()
            ts, readings, captured_monotonic = (
                self.pending_recording if self.pending_recording is not None
                else (time.time(), {}, started)
            )
            error = None

            if self.pending_recording is None:
                try:
                    with self._settings_lock:
                        rate = self._requested_rate
                        self._requested_rate = None
                    if rate is not None and hasattr(self.adc, "set_sample_rate"):
                        try:
                            self.adc.set_sample_rate(rate)
                        except Exception as exc:
                            raise GainConfigurationError(f"ADC configuration failed: {exc}") from exc
                    readings = read_scan(self.adc, self.channels, self.averaging, self.auto_gain)
                    self.last_scan_metadata = readings.metadata
                    self.clipped_scan_count += readings.metadata["clipped"]
                except Exception as e:
                    error = e
                    self._error_count += 1
                    if isinstance(e, GainConfigurationError):
                        self._running = False

            if error is None and self.recorder is not None:
                try:
                    def retry_status(exc):
                        if exc is None:
                            self.recording_retrying = False
                            self.recording_error = None
                        else:
                            self.auto_gain.reset_quiet()
                            first_failure = not self.recording_retrying
                            self.recording_retrying = True
                            self.recording_error = RuntimeError(
                                f"Storage unavailable; retrying every {self.recorder.retry_interval_sec} s: {exc}")
                            if first_failure:
                                for cb in list(self._callbacks):
                                    try:
                                        cb(ts, self.recording_error)
                                    except Exception:
                                        pass

                    if not self.recorder.write_with_retry(
                            ts, readings, self._stop_event, retry_status,
                            captured_monotonic=captured_monotonic):
                        self.pending_recording = (ts, readings, captured_monotonic)
                        break
                    self.pending_recording = None
                except Exception as exc:
                    self.recording_error = RuntimeError(f"Recording failed; acquisition stopped: {exc}")
                    self.recording_retrying = False
                    error = self.recording_error
                    self._running = False

            # Send either readings or error to callbacks
            data = error if error else readings
            for cb in list(self._callbacks):
                try:
                    cb(ts, data)
                except Exception:
                    pass

            elapsed = time.monotonic() - started
            to_sleep = period - elapsed
            if to_sleep > 0 and self._running:
                self._stop_event.wait(to_sleep)
