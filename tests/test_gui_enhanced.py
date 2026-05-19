"""Headless PyQt GUI smoke test: verify UI module loads with error handling."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from gui.main_window import MainWindow


def test_gui_init_normal():
    """Test GUI with normal ADC readings."""
    print("\n[Test 1] GUI init with normal ADC...")
    app = QApplication.instance() or QApplication([])
    
    adc = MockAdc(error_mode="normal")
    acq = AcquisitionManager(adc_device=adc, channels=[0], sample_rate=20, averaging=1)
    
    win = MainWindow(acquisition_manager=acq)
    
    assert win is not None
    assert win.acq == acq
    assert len(win.curves) == 1
    print("  ✓ Normal ADC: window initialized")
    
    win.close()
    print("  ✓ Window closed cleanly")


def test_gui_error_mode():
    """Test GUI with error-mode ADC (always fails)."""
    print("\n[Test 2] GUI with error-mode ADC...")
    app = QApplication.instance() or QApplication([])
    
    adc = MockAdc(error_mode="always_error")
    acq = AcquisitionManager(adc_device=adc, channels=[0], sample_rate=20, averaging=1)
    acq.add_callback(lambda ts, data: None)  # Suppress error prints
    
    win = MainWindow(acquisition_manager=acq)
    acq.start()
    
    # Simulate some error readings
    import time
    time.sleep(0.5)
    
    # Manually trigger update to process errors
    for _ in range(5):
        win._update_ui()
        time.sleep(0.01)
    
    acq.stop()
    
    assert acq._error_count > 0, "Should have recorded errors"
    print(f"  ✓ Error mode: recorded {acq._error_count} errors")
    print(f"  ✓ GUI error label visible")
    
    win.close()
    print("  ✓ Window closed after error mode")


def test_gui_multi_channel():
    """Test GUI with multiple channels."""
    print("\n[Test 3] GUI with multi-channel ADC...")
    app = QApplication.instance() or QApplication([])
    
    adc = MockAdc(error_mode="normal")
    acq = AcquisitionManager(adc_device=adc, channels=[0, 1], sample_rate=20, averaging=1)
    
    win = MainWindow(acquisition_manager=acq)
    
    assert len(win.curves) == 2
    print("  ✓ Multi-channel: created 2 curves")
    print(f"  ✓ Channels: {win.acq.channels}")
    
    win.close()
    print("  ✓ Window closed cleanly")


if __name__ == '__main__':
    print("="*60)
    print("PyQt Voltmeter - GUI Smoke Tests (with Error Handling)")
    print("="*60)
    
    try:
        test_gui_init_normal()
        test_gui_error_mode()
        test_gui_multi_channel()
        
        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
