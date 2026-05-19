"""Interactive PyQt GUI demo: opens window and shows live mock data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from gui.main_window import MainWindow


def main():
    """Run the GUI with mock ADC."""
    app = QApplication(sys.argv)
    
    print("Initializing mock ADC...")
    adc = MockAdc(amplitude=2.0, offset=2.5, freq=0.5)
    
    print("Creating acquisition manager...")
    acq = AcquisitionManager(
        adc_device=adc,
        channels=[0, 1],  # Multi-channel for demo
        sample_rate=50,
        averaging=1
    )
    
    print("Creating main window...")
    win = MainWindow(acquisition_manager=acq, max_points=500)
    win.setGeometry(100, 100, 1000, 600)
    win.show()
    
    print("Starting acquisition...")
    acq.start()
    
    print("\n" + "="*60)
    print("PyQt Voltmeter Demo is running!")
    print("- Live plot shows mock sine wave (0.5 Hz)")
    print("- Use spinner to adjust sample rate (1-10000 Hz)")
    print("- Click 'Stop' to pause acquisition")
    print("- Close window to exit")
    print("="*60 + "\n")
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
