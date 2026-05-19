"""Main PyQt6 window for the voltmeter UI with large voltage display and error handling."""
from collections import deque
from datetime import datetime
import csv
import os
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QComboBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)
import pyqtgraph as pg


class MainWindow(QMainWindow):
    def __init__(
        self,
        acquisition_manager,
        plot_window_sec: int = 60,
        plot_max_points: int = 2000,
        log_enabled: bool = True,
        log_dir: str = "logs",
    ):
        super().__init__()
        self.setWindowTitle("Voltmeter - PyQt")
        self.acq = acquisition_manager
        self.acq.add_callback(self._on_data)

        self.plot_window_sec = int(plot_window_sec)
        self.plot_max_points = int(plot_max_points)
        self._start_ts = None
        self._data_lock = threading.Lock()

        self._time_buffer = deque(maxlen=self._calc_maxlen())
        self.buffers = {
            ch: deque(maxlen=self._calc_maxlen())
            for ch in self.acq.channels
        }
        self._last = None
        self._last_error = None
        self._error_count = 0

        self._log_enabled = bool(log_enabled)
        self._log_dir = log_dir
        self._log_file = None
        self._log_writer = None
        self._log_header_written = False
        self._init_logging()

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
        self.voltage_label.setStyleSheet(
            "color: #2E7D32; background-color: #E8F5E9; padding: 20px; border-radius: 10px;")
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

        gain_label = QLabel("Gain:")
        control_layout.addWidget(gain_label)

        self.gain_combo = QComboBox()
        gain_options = self._get_gain_options()
        for g in gain_options:
            self.gain_combo.addItem(f"x{g}", g)
        self.gain_combo.currentIndexChanged.connect(self._change_gain)
        control_layout.addWidget(self.gain_combo)

        self.range_label = QLabel("Range: --")
        control_layout.addWidget(self.range_label)
        self._set_current_gain()
        control_layout.addStretch()

        v.addLayout(control_layout)

        # Plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Voltage", units="V")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setTitle("Voltage Trend")
        v.addWidget(self.plot_widget)

        self.curves = {}
        colors = ["#FF5722", "#2196F3", "#4CAF50",
                  "#FFC107", "#9C27B0", "#00BCD4"]
        for i, ch in enumerate(self.acq.channels):
            pen = pg.mkPen(color=colors[i % len(colors)], width=2)
            self.curves[ch] = self.plot_widget.plot(
                pen=pen, name=self._format_channel(ch))

    def _on_data(self, ts, readings):
        if isinstance(readings, Exception):
            self._last_error = readings
            self._error_count += 1
        else:
            self._last = readings
            self._last_error = None
            with self._data_lock:
                if self._start_ts is None:
                    self._start_ts = ts
                rel_ts = ts - self._start_ts
                self._time_buffer.append(rel_ts)
                for ch, v in readings.items():
                    self.buffers.setdefault(
                        ch, deque(maxlen=self._calc_maxlen())
                    ).append(v)
                self._log_reading(ts, rel_ts, readings)

    def _update_ui(self):
        if self._last_error is not None:
            # Show error
            self.voltage_label.setText("ERROR")
            self.voltage_label.setStyleSheet(
                "color: white; background-color: #C62828; padding: 20px; border-radius: 10px; font-weight: bold;")
            self.status_label.setText(
                f"⚠ {str(self._last_error)[:50]}... (Errors: {self._error_count})")
            self.status_label.setStyleSheet(
                "color: #C62828; padding: 10px; font-weight: bold;")
        elif self._last is not None:
            # Show voltage
            if len(self.acq.channels) == 1:
                ch = self.acq.channels[0]
                v = self._last.get(ch, 0.0)
                self.voltage_label.setText(self._format_voltage(v))
            else:
                # Multi-channel: show all
                values = " | ".join(
                    f"{self._format_channel(ch)}: {self._format_voltage(self._last.get(ch, 0.0))}"
                    for ch in self.acq.channels
                )
                self.voltage_label.setText(values)

            self.voltage_label.setStyleSheet(
                "color: #2E7D32; background-color: #E8F5E9; padding: 20px; border-radius: 10px;")
            self.status_label.setText("✓ Connected")
            self.status_label.setStyleSheet("color: #2E7D32; padding: 10px;")
        else:
            self.voltage_label.setText("-- V")
            self.status_label.setText("Waiting for data...")

        with self._data_lock:
            times = list(self._time_buffer)
            for ch, curve in self.curves.items():
                data = list(self.buffers.get(ch, []))
                if data and times:
                    x, y = self._downsample(times, data)
                    curve.setData(x, y)

    def _toggle(self):
        if getattr(self.acq, "_running", False):
            self.acq.stop()
            self.start_btn.setText("Start")
        else:
            self.acq.start()
            self.start_btn.setText("Stop")

    def _change_rate(self, val: int):
        if hasattr(self.acq, "set_sample_rate"):
            self.acq.set_sample_rate(float(val))
        else:
            self.acq.sample_rate = float(val)
        self._resize_buffers()

    def _change_gain(self):
        gain = self.gain_combo.currentData()
        if gain is None:
            return
        adc = getattr(self.acq, "adc", None)
        if adc and hasattr(adc, "set_gain"):
            try:
                adc.set_gain(int(gain))
            except Exception:
                pass
        self._update_range_label()

    def _get_gain_options(self):
        adc = getattr(self.acq, "adc", None)
        if adc and hasattr(adc, "GAIN_MAP"):
            return sorted(list(adc.GAIN_MAP.keys()))
        return [1, 2, 4, 8, 16, 32, 64]

    def _set_current_gain(self):
        adc = getattr(self.acq, "adc", None)
        current = getattr(adc, "gain", 1)
        for i in range(self.gain_combo.count()):
            if self.gain_combo.itemData(i) == current:
                self.gain_combo.setCurrentIndex(i)
                break
        self._update_range_label()

    def _update_range_label(self):
        adc = getattr(self.acq, "adc", None)
        vref = float(getattr(adc, "vref", 2.5))
        gain = float(getattr(adc, "gain", 1))
        single_ended = bool(getattr(adc, "single_ended", True))
        full_scale = vref / max(gain, 1.0)
        if not single_ended:
            full_scale *= 2.0
        unit, scale, decimals = self._select_unit(full_scale)
        fs_scaled = full_scale * scale
        if single_ended:
            text = f"Range: 0-{fs_scaled:.{decimals}f} {unit}"
        else:
            text = f"Range: -{fs_scaled:.{decimals}f} to {fs_scaled:.{decimals}f} {unit}"
        self.range_label.setText(text)

    def _select_unit(self, full_scale_v: float):
        # Pick unit based on range from gain selection.
        if full_scale_v <= 0.01:
            return "uV", 1_000_000.0, 0
        if full_scale_v <= 1.0:
            return "mV", 1_000.0, 4
        return "V", 1.0, 6

    def _format_voltage(self, value_v: float) -> str:
        adc = getattr(self.acq, "adc", None)
        vref = float(getattr(adc, "vref", 2.5))
        gain = float(getattr(adc, "gain", 1))
        single_ended = bool(getattr(adc, "single_ended", True))
        full_scale = vref / max(gain, 1.0)
        if not single_ended:
            full_scale *= 2.0
        unit, scale, decimals = self._select_unit(full_scale)
        return f"{value_v * scale:.{decimals}f} {unit}"

    def _format_channel(self, channel) -> str:
        if isinstance(channel, (tuple, list)) and len(channel) == 2:
            return f"AD{channel[0]}-AD{channel[1]}"
        return f"CH{channel}"

    def _calc_maxlen(self) -> int:
        rate = float(getattr(self.acq, "sample_rate", 1.0))
        return max(int(self.plot_window_sec * max(rate, 1.0)), 10)

    def _resize_buffers(self):
        new_len = self._calc_maxlen()
        with self._data_lock:
            self._time_buffer = deque(self._time_buffer, maxlen=new_len)
            for ch in self.acq.channels:
                current = self.buffers.get(ch, deque())
                self.buffers[ch] = deque(current, maxlen=new_len)

    def _downsample(self, x_vals, y_vals):
        if self.plot_max_points <= 0 or len(x_vals) <= self.plot_max_points:
            return x_vals, y_vals
        step = max(1, int(len(x_vals) / self.plot_max_points))
        return x_vals[::step], y_vals[::step]

    def _init_logging(self):
        if not self._log_enabled:
            return
        os.makedirs(self._log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"voltmeter_{stamp}.csv"
        path = os.path.join(self._log_dir, filename)
        self._log_file = open(path, "w", newline="", encoding="utf-8")
        self._log_writer = csv.writer(self._log_file)

    def _log_reading(self, ts, rel_ts, readings):
        if not self._log_enabled or self._log_writer is None:
            return
        if not self._log_header_written:
            header = ["timestamp", "elapsed_s"] + \
                [f"ch{ch}" for ch in readings.keys()]
            self._log_writer.writerow(header)
            self._log_header_written = True
        iso_ts = datetime.fromtimestamp(ts).isoformat()
        row = [iso_ts, f"{rel_ts:.6f}"] + \
            [f"{readings[ch]:.6f}" for ch in readings.keys()]
        self._log_writer.writerow(row)
        self._log_file.flush()

    def closeEvent(self, event):
        if self._log_file:
            try:
                self._log_file.flush()
                self._log_file.close()
            except Exception:
                pass
        event.accept()
