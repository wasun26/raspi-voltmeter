"""Headless PyQt GUI smoke test: verify UI module loads without hardware."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from gui.main_window import MainWindow


def test_gui_init():
    """Create app, manager, and main window without displaying."""
    app = QApplication.instance() or QApplication([])
    
    adc = MockAdc()
    acq = AcquisitionManager(adc_device=adc, channels=[0], sample_rate=20, averaging=1)
    
    win = MainWindow(acquisition_manager=acq)
    
    # Verify window is created
    assert win is not None
    assert win.acq == acq
    assert len(win.curves) == 1
    assert 0 in win.curves
    print("✓ GUI init successful")
    print(f"  - Window title: {win.windowTitle()}")
    print(f"  - Channels: {win.acq.channels}")
    print(f"  - Sample rate: {win.acq.sample_rate} Hz")
    
    win.close()
    print("✓ GUI closed cleanly")


if __name__ == '__main__':
    test_gui_init()
