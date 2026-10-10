"""Main PyQt6 window for the voltmeter UI with large voltage display and error handling."""
from collections import deque
from datetime import datetime
import threading

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.chart import create_plot_widget, make_pen
from core.recording import CsvRecorder


class MainWindow(QMainWindow):
    def __init__(
        self,
        acquisition_manager,
        plot_window_sec: int = 60,
        plot_max_points: int = 2000,
    ):
        super().__init__()
        self.setWindowTitle("Voltmeter - PyQt")
        self.resize(960, 760)
        self.setMinimumSize(720, 620)
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

        self._setup_ui()

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui)
        self.timer.start()

    def _setup_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout()
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)
        w.setLayout(v)

        # Voltage display section
        display_layout = QVBoxLayout()
        display_layout.setSpacing(4)
        display_layout.setContentsMargins(0, 0, 0, 0)

        self.source_label = QLabel(
            f"{type(self.acq.adc).__name__} | "
            + ", ".join(self._format_channel(ch) for ch in self.acq.channels)
        )
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if type(self.acq.adc).__name__ == "MockAdc":
            self.source_label.setText(self.source_label.text() + " | SIMULATED DATA")
            self.source_label.setStyleSheet("color: #9A6700; font-weight: bold;")
        display_layout.addWidget(self.source_label)

        # Large voltage readout
        self.voltage_label = QLabel("-- mV")
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        large_font = QFont()
        large_font.setPointSize(36)
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

        self.start_btn = QPushButton("Pause measurement")
        self.start_btn.setMinimumWidth(155)
        self.start_btn.setToolTip("Pause both measurement and CSV recording; saved data is kept.")
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

        recording_group = QGroupBox("Save data — CSV")
        recording_layout = QGridLayout(recording_group)
        recording_layout.setContentsMargins(12, 12, 12, 12)
        recording_layout.setHorizontalSpacing(12)
        recording_layout.setVerticalSpacing(8)
        self.recording_label = QLabel("Waiting for first sample")
        self.recording_label.setWordWrap(True)
        recording_layout.addWidget(self.recording_label, 0, 0, 1, 3)
        self.saved_count_label = QLabel("Saved samples: 0")
        self.last_saved_label = QLabel("Last saved: —")
        recording_layout.addWidget(self.saved_count_label, 1, 0)
        recording_layout.addWidget(self.last_saved_label, 1, 1, 1, 2)

        self.folder_field = QLineEdit()
        self.file_field = QLineEdit()
        for field in (self.folder_field, self.file_field):
            field.setReadOnly(True)
            field.setMinimumWidth(0)
        recording_layout.addWidget(QLabel("Folder"), 2, 0)
        recording_layout.addWidget(self.folder_field, 2, 1, 1, 2)
        recording_layout.addWidget(QLabel("Current file"), 3, 0)
        recording_layout.addWidget(self.file_field, 3, 1, 1, 2)

        actions = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open folder")
        self.open_folder_btn.clicked.connect(self._open_log_folder)
        self.copy_path_btn = QPushButton("Copy file path")
        self.copy_path_btn.clicked.connect(self._copy_log_path)
        self.change_folder_btn = QPushButton("Change folder…")
        self.change_folder_btn.clicked.connect(self._choose_log_folder)
        self.change_folder_btn.setToolTip("Pause measurement first. Changing folder starts a new recording session.")
        for button in (self.open_folder_btn, self.copy_path_btn, self.change_folder_btn):
            actions.addWidget(button)
        actions.addStretch()
        recording_layout.addLayout(actions, 4, 0, 1, 3)
        hint = QLabel("Auto-save every reading in mV • New file each day • Pause stops measurement and saving")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        recording_layout.addWidget(hint, 5, 0, 1, 3)
        recording_layout.setColumnStretch(1, 1)
        v.addWidget(recording_group)

        # Plot
        self.plot_widget = create_plot_widget()
        self.plot_widget.setLabel("left", "Voltage", units="mV")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setTitle("Voltage Trend")
        v.addWidget(self.plot_widget, 1)

        self.curves = {}
        colors = ["#FF5722", "#2196F3", "#4CAF50",
                  "#FFC107", "#9C27B0", "#00BCD4"]
        for i, ch in enumerate(self.acq.channels):
            pen = make_pen(color=colors[i % len(colors)], width=2)
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

    def _update_ui(self):
        self._update_recording_ui()
        if self._last_error is not None:
            self.voltage_label.setText("ERROR")
            self.voltage_label.setStyleSheet(
                "color: white; background-color: #C62828; padding: 20px; border-radius: 10px; font-weight: bold;")
            self.status_label.setText(f"{self._last_error} (Errors: {self._error_count})")
            self.status_label.setWordWrap(True)
            self.status_label.setStyleSheet("color: #C62828; padding: 4px; font-weight: bold;")
        elif self._last is not None:
            if len(self.acq.channels) == 1:
                self.voltage_label.setText(self._format_voltage(self._last.get(self.acq.channels[0], 0.0)))
            else:
                self.voltage_label.setText(" | ".join(
                    f"{self._format_channel(ch)}: {self._format_voltage(self._last.get(ch, 0.0))}"
                    for ch in self.acq.channels))
            self.voltage_label.setStyleSheet(
                "color: #2E7D32; background-color: #E8F5E9; padding: 20px; border-radius: 10px;")
            self.status_label.setText("Measuring" if self.acq._running else "Paused — last measured value")
            self.status_label.setStyleSheet("color: #666; padding: 4px;")
        else:
            self.voltage_label.setText("-- mV")
            self.status_label.setText("Waiting for data..." if self.acq._running else "Ready to start")

        with self._data_lock:
            times = list(self._time_buffer)
            for ch, curve in self.curves.items():
                data = list(self.buffers.get(ch, []))
                if data and times:
                    x, y = self._downsample(times, data)
                    curve.setData(x, [value * 1000.0 for value in y])

    def _update_recording_ui(self):
        recorder = self.acq.recorder
        failed = self.acq.recording_error is not None
        running = self.acq._running
        self.start_btn.setEnabled(not failed)
        self.start_btn.setText("Stopped" if failed else "Pause measurement" if running else "Start measurement")
        self.change_folder_btn.setEnabled(recorder is not None and not running and not failed)
        self.open_folder_btn.setEnabled(recorder is not None)
        self.copy_path_btn.setEnabled(recorder is not None and recorder.path is not None)
        if failed:
            state, color = str(self.acq.recording_error), "#C62828"
        elif recorder is None:
            state, color = "Saving disabled - measurements are not recorded", "#9A6700"
        elif not running:
            state, color = "Paused - saved files are kept", "#9A6700"
        elif self._last_error is not None:
            state, color = "Waiting for valid ADC data - no new samples saved", "#9A6700"
        elif recorder.saved_count:
            state, color = "Saving automatically - CSV", "#2E7D32"
        else:
            state, color = "Waiting for first saved sample", "#666"
        self.recording_label.setText(state)
        self.recording_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        count = recorder.saved_count if recorder else 0
        self.saved_count_label.setText(f"Saved samples: {count:,}")
        timestamp = recorder.last_saved_timestamp if recorder else None
        last_saved = datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if timestamp is not None else "None yet"
        self.last_saved_label.setText(f"Last saved: {last_saved}")
        folder = str(recorder.directory) if recorder else "Saving disabled in config.py"
        filename = recorder.path.name if recorder and recorder.path else "Created after first reading" if recorder else "Saving disabled"
        for field, value in ((self.folder_field, folder), (self.file_field, filename)):
            if field.text() != value:
                field.setText(value)
                field.setCursorPosition(0)
            field.setToolTip(value)

    def _open_log_folder(self):
        recorder = self.acq.recorder
        if recorder and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(recorder.directory))):
            QMessageBox.warning(self, "Open folder", "Could not open the folder. Copy the path from the Folder field.")

    def _copy_log_path(self):
        recorder = self.acq.recorder
        if recorder and recorder.path:
            QApplication.clipboard().setText(str(recorder.path))

    def _choose_log_folder(self):
        recorder = self.acq.recorder
        if recorder is None or self.acq._running or self.acq.recording_error is not None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose recording folder", str(recorder.directory))
        if not folder or folder == str(recorder.directory):
            return
        try:
            replacement = CsvRecorder(folder, self.acq.channels, self.acq.adc, self.acq.averaging)
        except Exception as exc:
            QMessageBox.warning(self, "Recording folder", f"Could not use this folder: {exc}")
            return
        try:
            recorder.close()
        except Exception as exc:
            replacement.close()
            self.acq.recording_error = RuntimeError(f"Recording close failed: {exc}")
            self._update_ui()
            return
        self.acq.recorder = replacement
        self._update_recording_ui()

    def _toggle(self):
        if self.acq.recording_error is not None:
            return
        if self.acq._running:
            self.acq.stop()
        else:
            self.acq.start()
        self._update_ui()

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

    def closeEvent(self, event):
        self.timer.stop()
        self.acq.stop()
        if self.acq.recorder is not None:
            self.acq.recorder.close()
        event.accept()
