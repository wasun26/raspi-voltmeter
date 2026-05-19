"""Main PyQt6 window for the voltmeter UI with large voltage display and error handling."""
from collections import deque

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)
import pyqtgraph as pg


class MainWindow(QMainWindow):
    def __init__(self, acquisition_manager, max_points: int = 1000):
        super().__init__()
        self.setWindowTitle("Voltmeter - PyQt")
        self.acq = acquisition_manager
        self.acq.add_callback(self._on_data)

        self.max_points = max_points
        self.buffers = {ch: deque(maxlen=self.max_points) for ch in self.acq.channels}
        self._last = None
        self._last_error = None
        self._error_count = 0

        self._setup_ui()

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui)
        self.timer.start()

    def _setup_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout()
        w.setLayout(v)

        # Voltage display section
        display_layout = QVBoxLayout()
        display_layout.setSpacing(10)
        display_layout.setContentsMargins(20, 20, 20, 20)

        # Large voltage readout
        self.voltage_label = QLabel("-- V")
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        large_font = QFont()
        large_font.setPointSize(48)
        large_font.setBold(True)
        self.voltage_label.setFont(large_font)
        self.voltage_label.setStyleSheet("color: #2E7D32; background-color: #E8F5E9; padding: 20px; border-radius: 10px;")
        display_layout.addWidget(self.voltage_label)

        # Status/error message
        self.status_label = QLabel("Waiting for data...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(12)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("color: #666; padding: 10px;")
        display_layout.addWidget(self.status_label)

        v.addLayout(display_layout)

        # Control panel
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)

        self.start_btn = QPushButton("Stop")
        self.start_btn.setMinimumWidth(80)
        self.start_btn.clicked.connect(self._toggle)
        control_layout.addWidget(self.start_btn)

        rate_label = QLabel("Sample Rate (Hz):")
        control_layout.addWidget(rate_label)

        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(1, 10000)
        self.rate_spin.setValue(int(self.acq.sample_rate))
        self.rate_spin.valueChanged.connect(self._change_rate)
        control_layout.addWidget(self.rate_spin)
        control_layout.addStretch()

        v.addLayout(control_layout)

        # Plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Voltage", units="V")
        self.plot_widget.setLabel("bottom", "Sample")
        self.plot_widget.setTitle("Voltage Trend")
        v.addWidget(self.plot_widget)

        self.curves = {}
        colors = ["#FF5722", "#2196F3", "#4CAF50", "#FFC107", "#9C27B0", "#00BCD4"]
        for i, ch in enumerate(self.acq.channels):
            pen = pg.mkPen(color=colors[i % len(colors)], width=2)
            self.curves[ch] = self.plot_widget.plot(pen=pen, name=f"Channel {ch}")

    def _on_data(self, ts, readings):
        if isinstance(readings, Exception):
            self._last_error = readings
            self._error_count += 1
        else:
            self._last = readings
            self._last_error = None
            for ch, v in readings.items():
                self.buffers.setdefault(ch, deque(maxlen=self.max_points)).append(v)

    def _update_ui(self):
        if self._last_error is not None:
            # Show error
            self.voltage_label.setText("ERROR")
            self.voltage_label.setStyleSheet("color: white; background-color: #C62828; padding: 20px; border-radius: 10px; font-weight: bold;")
            self.status_label.setText(f"⚠ {str(self._last_error)[:50]}... (Errors: {self._error_count})")
            self.status_label.setStyleSheet("color: #C62828; padding: 10px; font-weight: bold;")
        elif self._last is not None:
            # Show voltage
            if len(self.acq.channels) == 1:
                ch = self.acq.channels[0]
                v = self._last.get(ch, 0.0)
                self.voltage_label.setText(f"{v:.3f} V")
            else:
                # Multi-channel: show all
                values = " | ".join(f"CH{ch}: {self._last.get(ch, 0.0):.3f}V" for ch in self.acq.channels)
                self.voltage_label.setText(values)
            
            self.voltage_label.setStyleSheet("color: #2E7D32; background-color: #E8F5E9; padding: 20px; border-radius: 10px;")
            self.status_label.setText("✓ Connected")
            self.status_label.setStyleSheet("color: #2E7D32; padding: 10px;")
        else:
            self.voltage_label.setText("-- V")
            self.status_label.setText("Waiting for data...")

        for ch, curve in self.curves.items():
            data = list(self.buffers.get(ch, []))
            if data:
                curve.setData(data)

    def _toggle(self):
        if getattr(self.acq, "_running", False):
            self.acq.stop()
            self.start_btn.setText("Start")
        else:
            self.acq.start()
            self.start_btn.setText("Stop")

    def _change_rate(self, val: int):
        self.acq.sample_rate = float(val)
