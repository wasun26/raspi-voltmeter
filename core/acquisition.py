"""Acquisition manager: reads ADC periodically and delivers samples to callbacks."""
import threading
import time
from typing import Callable, List


class AcquisitionManager:
    """Simple acquisition manager that polls an AdcDevice in a background thread."""

    def __init__(self, adc_device, channels: List[int] = [0], sample_rate: float = 10.0, averaging: int = 1):
        self.adc = adc_device
        self.channels = list(channels)
        self.sample_rate = float(sample_rate)
        self.averaging = int(averaging)

        self._callbacks: List[Callable] = []
        self._running = False
        self._thread = None
        self._error_count = 0

    def add_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        period = 1.0 / self.sample_rate if self.sample_rate > 0 else 0.1
        while self._running:
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

            # Send either readings or error to callbacks
            data = error if error else readings
            for cb in list(self._callbacks):
                try:
                    cb(ts, data)
                except Exception:
                    pass

            elapsed = time.time() - ts
            to_sleep = period - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)
