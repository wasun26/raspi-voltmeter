"""Interactive GUI test with error simulation modes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
)
from PyQt6.QtCore import Qt, QTimer

from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from gui.main_window import MainWindow as VoltmeterWindow


class TestDemoWindow(QMainWindow):
    """Test harness window with mode selector and multiple volt display modes."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt Voltmeter - Test Demo with Error Simulation")
        self.setGeometry(50, 50, 1200, 800)

        # Current configuration
        self.current_mode = "normal"
        self.error_rate = 0.1

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Control panel
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Test Mode:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["normal", "random_error", "always_error", "stuck"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        ctrl_layout.addWidget(self.mode_combo)

        self.status_label = QLabel("Press 'Start Demo' to begin...")
        self.status_label.setStyleSheet("color: #666; font-weight: bold;")
        ctrl_layout.addWidget(self.status_label)

        self.start_btn = QPushButton("Start Demo")
        self.start_btn.clicked.connect(self._start_demo)
        ctrl_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop_demo)
        self.stop_btn.setEnabled(False)
        ctrl_layout.addWidget(self.stop_btn)

        layout.addLayout(ctrl_layout)

        # Instructions
        instructions = QLabel(
            "Test Modes:\n"
            "  • normal: Smooth sine wave (0-3V)\n"
            "  • random_error: Occasional communication errors (~10% chance)\n"
            "  • always_error: Continuous errors (red display, error count)\n"
            "  • stuck: ADC returns constant value\n\n"
            "Watch the large voltage display - it should show green when data is OK,\n"
            "and red with error message when ADC communication fails."
        )
        instructions.setStyleSheet("background-color: #F5F5F5; padding: 10px; border-radius: 5px;")
        layout.addWidget(instructions)

        # Voltmeter window placeholder
        self.voltmeter_widget = None
        self.acq = None

        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status)

    def _on_mode_changed(self, new_mode):
        self.current_mode = new_mode
        self.status_label.setText(f"Mode: {new_mode}")

    def _start_demo(self):
        """Start a new voltmeter with the selected test mode."""
        if self.voltmeter_widget:
            # Stop existing demo
            if self.acq:
                self.acq.stop()
            self.voltmeter_widget.close()

        # Create mock ADC with selected mode
        error_mode = self.current_mode if self.current_mode != "normal" else "normal"
        if error_mode == "random_error":
            adc = MockAdc(amplitude=1.5, offset=1.5, freq=0.5, 
                         error_mode="random", error_rate=0.1)
        elif error_mode == "always_error":
            adc = MockAdc(amplitude=1.5, offset=1.5, freq=0.5,
                         error_mode="always_error")
        elif error_mode == "stuck":
            adc = MockAdc(amplitude=1.5, offset=1.5, freq=0.5,
                         error_mode="stuck")
        else:
            adc = MockAdc(amplitude=1.5, offset=1.5, freq=0.5)

        # Create acquisition manager
        self.acq = AcquisitionManager(
            adc_device=adc,
            channels=[0],
            sample_rate=50,
            averaging=1,
        )

        # Create voltmeter window
        self.voltmeter_widget = VoltmeterWindow(acquisition_manager=self.acq, max_points=200)
        self.voltmeter_widget.setGeometry(50, 350, 1100, 450)
        self.voltmeter_widget.show()

        # Start acquisition
        self.acq.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.mode_combo.setEnabled(False)
        self.status_label.setText(f"Demo running in '{self.current_mode}' mode...")
        self.timer.start(1000)

    def _stop_demo(self):
        """Stop the voltmeter demo."""
        if self.acq:
            self.acq.stop()
        if self.voltmeter_widget:
            self.voltmeter_widget.close()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.mode_combo.setEnabled(True)
        self.status_label.setText("Demo stopped. Select a mode and click 'Start Demo' to continue.")
        self.timer.stop()

    def _update_status(self):
        if self.acq:
            error_count = getattr(self.acq, "_error_count", 0)
            # Status is updated in the voltmeter window itself
            pass

    def closeEvent(self, event):
        if self.acq:
            self.acq.stop()
        if self.voltmeter_widget:
            self.voltmeter_widget.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    demo = TestDemoWindow()
    demo.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
