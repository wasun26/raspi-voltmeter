import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager


def main():
    samples = []

    def cb(ts, readings):
        samples.append((ts, readings))
        print(f"{ts:.3f}: {readings}")

    adc = MockAdc()
    acq = AcquisitionManager(adc_device=adc, channels=[0], sample_rate=50, averaging=1)
    acq.add_callback(cb)
    acq.start()
    time.sleep(1.0)
    acq.stop()

    print("Collected", len(samples), "samples")
    if samples:
        print("Example:", samples[0])


if __name__ == '__main__':
    main()
