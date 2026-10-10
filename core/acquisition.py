"""Acquisition manager: reads ADC periodically and delivers samples to callbacks."""
import threading
import time
from typing import Callable, List


class AcquisitionManager:
    """Simple acquisition manager that polls an AdcDevice in a background thread."""

    def __init__(self, adc_device, channels: List[int] = [0], sample_rate: float = 10.0, averaging: int = 1, recorder=None):
        self.adc = adc_device
        self.channels = list(channels)
        self.sample_rate = float(sample_rate)
        self.averaging = int(averaging)
        self.recorder = recorder
        self.recording_error = None
        self._stop_event = threading.Event()

        self._callbacks: List[Callable] = []
        self._running = False
        self._thread = None
        self._error_count = 0

    def add_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def start(self):
        if self.recording_error is not None:
            raise RuntimeError("Recording failed; restart after fixing storage") from self.recording_error
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self.set_sample_rate(self.sample_rate)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()

    def set_sample_rate(self, rate_hz: float):
        self.sample_rate = float(rate_hz)
        if hasattr(self.adc, "set_sample_rate"):
            try:
                self.adc.set_sample_rate(self.sample_rate)
            except Exception:
                pass

    def _run(self):
        while self._running:
            period = 1.0 / self.sample_rate if self.sample_rate > 0 else 0.1
            started = time.monotonic()
            ts = time.time()
            readings = {}
            error = None

            try:
                for ch in self.channels:
                    if self.averaging <= 1:
                        v = self.adc.read_voltage(ch)
                    else:
                        s = 0.0
                        for _ in range(self.averaging):
                            s += self.adc.read_voltage(ch)
                        v = s / self.averaging
                    readings[ch] = v
            except Exception as e:
                error = e
                self._error_count += 1

            if error is None and self.recorder is not None:
                try:
                    self.recorder.write(ts, readings)
                except Exception as exc:
                    self.recording_error = RuntimeError(f"Recording failed; acquisition stopped: {exc}")
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
