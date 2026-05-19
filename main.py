import sys
from PyQt6.QtWidgets import QApplication

from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from gui.main_window import MainWindow


def main():
    adc = MockAdc()
    acq = AcquisitionManager(adc_device=adc, channels=[0], sample_rate=20, averaging=1)

    app = QApplication(sys.argv)
    win = MainWindow(acquisition_manager=acq)
    win.show()

    acq.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
