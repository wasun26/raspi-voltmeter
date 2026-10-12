"""Main PyQt6 window for the voltmeter UI with large voltage display and error handling."""
from collections import deque
from datetime import datetime
import threading

from PyQt6.QtCore import QEvent, QLocale, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QDialog,
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
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from gui.chart import create_plot_widget, make_pen
from core.recording import CsvRecorder
from config import save_recording_settings
from gui.recording_settings import RecordingSettingsDialog
from app_version import APP_VERSION


class MainWindow(QMainWindow):
    _error_received = pyqtSignal()

    def __init__(
        self,
        acquisition_manager,
        plot_window_sec: int = 60,
        plot_max_points: int = 2000,
        collection_mode: bool = False,
        collection_ui_refresh_ms: int = 3000,
    ):
        super().__init__()
        self.setLocale(QLocale.c())
        self.setWindowTitle(f"Voltmeter v{APP_VERSION}")
        self.resize(960, 760)
        self.setMinimumSize(720, 740)
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
        self._collection_mode = False
        self._collection_ui_refresh_ms = max(1000, int(collection_ui_refresh_ms))
        self._monitor_layout = None
        self._plot_active = False
        self._chart_presented = False
        self._plot_revision = 0
        self._last_plot_revision = -1
        self._closing = False
        self.update_requested = False
        self.update_error_detail = ""
        self._was_running_before_update = False
        self._recorder_before_update = None

        self._setup_ui()
        self._setup_menus()
        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui)
        self._error_received.connect(self._update_ui)
        self.chart_dock.visibilityChanged.connect(self._on_chart_visibility_changed)
        self.timer.start()
        self._refresh_plot_state()
        self._update_ui()
        if collection_mode:
            self.collection_mode_action.setChecked(True)

    def _setup_ui(self):
        w = QWidget()
        # All three work areas are docks so each can be moved or tabified.
        center = QWidget()
        self.setCentralWidget(center)
        center.hide()
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
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
        self.display_layout = display_layout
        self.voltage_font = large_font

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

        rate_label = QLabel("Sample Rate:")
        control_layout.addWidget(rate_label)

        self.rate_spin = QSpinBox()
        self.rate_spin.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.rate_spin.setGroupSeparatorShown(True)
        self.rate_spin.setRange(1, 10000)
        self.rate_spin.setValue(int(self.acq.sample_rate))
        self.rate_spin.valueChanged.connect(self._change_rate)
        control_layout.addWidget(self.rate_spin)
        control_layout.addWidget(QLabel("Hz"))

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
        self.measurement_dock = self._create_dock("Measurement", "measurement_dock", w)

        recording_group = QGroupBox()
        self.recording_group = recording_group
        recording_layout = QGridLayout(recording_group)
        recording_layout.setContentsMargins(12, 12, 12, 12)
        recording_layout.setHorizontalSpacing(12)
        recording_layout.setVerticalSpacing(8)
        self.recording_layout = recording_layout
        self.recording_label = QLabel("Waiting for first sample")
        self.recording_label.setWordWrap(True)
        recording_layout.addWidget(self.recording_label, 1, 0, 1, 3)
        self.saved_count_label = QLabel("Saved samples: 0")
        self.last_saved_label = QLabel("Last saved: —")
        recording_layout.addWidget(self.saved_count_label, 2, 0)
        recording_layout.addWidget(self.last_saved_label, 2, 1, 1, 2)
        self.file_info_label = QLabel()
        self.file_info_label.setWordWrap(True)
        recording_layout.addWidget(self.file_info_label, 3, 0, 1, 3)

        self.folder_field = QLineEdit()
        self.file_field = QLineEdit()
        for field in (self.folder_field, self.file_field):
            field.setReadOnly(True)
            field.setMinimumWidth(0)
        recording_layout.addWidget(QLabel("Folder"), 4, 0)
        recording_layout.addWidget(self.folder_field, 4, 1, 1, 2)
        recording_layout.addWidget(QLabel("Current file"), 5, 0)
        recording_layout.addWidget(self.file_field, 5, 1, 1, 2)

        actions = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open folder")
        self.open_folder_btn.clicked.connect(self._open_log_folder)
        self.copy_path_btn = QPushButton("Copy file path")
        self.copy_path_btn.clicked.connect(self._copy_log_path)
        self.change_folder_btn = QPushButton("Change folder…")
        self.change_folder_btn.clicked.connect(self._choose_log_folder)
        self.change_folder_btn.setToolTip("Pause measurement first. Changing folder starts a new recording session.")
        self.recording_settings_btn = QPushButton("Settings…")
        self.recording_settings_btn.clicked.connect(self._show_recording_settings)
        self.recording_settings_btn.setToolTip("Pause first to apply recording settings and start a new session.")
        for button in (self.open_folder_btn, self.copy_path_btn, self.change_folder_btn, self.recording_settings_btn):
            actions.addWidget(button)
        actions.addStretch()
        recording_layout.addLayout(actions, 6, 0, 1, 3)
        hint = QLabel("Auto-save every reading in mV • Pause stops measurement and saving • Existing files are kept")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        recording_layout.addWidget(hint, 7, 0, 1, 3)
        recording_layout.setColumnStretch(1, 1)
        recording_layout.setRowStretch(8, 1)
        self.recording_dock = self._create_dock("Save data", "recording_dock", recording_group)

        # Plot
        self.plot_widget = create_plot_widget()
        self.plot_widget.setMinimumHeight(160)
        self.plot_widget.setLabel("left", "Voltage", units="mV")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setTitle("Voltage Trend")
        self.chart_dock = self._create_dock("Voltage trend", "chart_dock", self.plot_widget)

        self.curves = {}
        colors = ["#FF5722", "#2196F3", "#4CAF50",
                  "#FFC107", "#9C27B0", "#00BCD4"]
        for i, ch in enumerate(self.acq.channels):
            pen = make_pen(color=colors[i % len(colors)], width=2)
            self.curves[ch] = self.plot_widget.plot(
                pen=pen, name=self._format_channel(ch))

        self.splitDockWidget(self.measurement_dock, self.recording_dock, Qt.Orientation.Vertical)
        self.splitDockWidget(self.recording_dock, self.chart_dock, Qt.Orientation.Vertical)
        self.resizeDocks(
            [self.measurement_dock, self.recording_dock, self.chart_dock],
            [220, 210, 280], Qt.Orientation.Vertical,
        )
        self._default_dock_state = self.saveState()

    def _create_dock(self, title, name, content):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setWidget(content)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        return dock

    def _reset_panel_layout(self):
        self.restoreState(self._default_dock_state)
        for dock in (self.measurement_dock, self.recording_dock, self.chart_dock):
            dock.show()
        self.resizeDocks(
            [self.measurement_dock, self.recording_dock, self.chart_dock],
            [220, 210, 280], Qt.Orientation.Vertical,
        )
        if self._collection_mode:
            # Return to the reset layout when live view is requested later.
            self._monitor_layout = self.saveState()
            self.measurement_dock.hide()
            self.chart_dock.hide()
            self.recording_dock.show()
            self.recording_dock.raise_()
        self._refresh_plot_state()

    def _setup_menus(self):
        menu_bar = self.menuBar()
        # Keep the menu inside the window on Raspberry Pi OS and Windows.
        menu_bar.setNativeMenuBar(False)

        def action(menu, text, callback, shortcut=None):
            item = QAction(text, self)
            if shortcut is not None:
                item.setShortcut(shortcut)
            item.triggered.connect(callback)
            menu.addAction(item)
            return item

        file_menu = menu_bar.addMenu("&File")
        self.open_folder_action = action(file_menu, "&Open recording folder", self._open_log_folder, "Ctrl+O")
        self.change_folder_action = action(file_menu, "&Change recording folder…", self._choose_log_folder, "Ctrl+Shift+O")
        self.copy_path_action = action(file_menu, "&Copy file path", self._copy_log_path, "Ctrl+Shift+C")
        self.recording_settings_action = action(file_menu, "Recording &settings…", self._show_recording_settings, "Ctrl+,")
        file_menu.addSeparator()
        self.collection_mode_action = QAction("Data collection mode", self)
        self.collection_mode_action.setCheckable(True)
        self.collection_mode_action.setShortcut("Ctrl+M")
        self.collection_mode_action.setToolTip("Keep recording every reading; stop graph work and update status slowly.")
        self.collection_mode_action.toggled.connect(self._set_collection_mode)
        file_menu.addAction(self.collection_mode_action)
        file_menu.addSeparator()
        action(file_menu, "E&xit", self.close, "Ctrl+Q")

        self.measurement_action = QAction(self)
        self.measurement_action.setShortcut("Ctrl+Space")
        self.measurement_action.triggered.connect(self._toggle)
        self.addAction(self.measurement_action)

        mode_toolbar = QToolBar("Recording controls", self)
        mode_toolbar.setObjectName("recording_controls_toolbar")
        mode_toolbar.setMovable(False)
        mode_toolbar.addAction(self.collection_mode_action)
        mode_toolbar.addSeparator()
        mode_toolbar.addAction(self.measurement_action)
        mode_toolbar.addSeparator()
        self.update_action = QAction("Check for updates", self)
        self.update_action.triggered.connect(self._show_update_dialog)
        mode_toolbar.addAction(self.update_action)
        self.addToolBar(mode_toolbar)
        self.mode_label = QLabel()
        self.statusBar().addWidget(self.mode_label, 1)

        view_menu = menu_bar.addMenu("&View")
        self.recording_panel_action = self.recording_dock.toggleViewAction()
        for dock in (self.measurement_dock, self.recording_dock, self.chart_dock):
            view_menu.addAction(dock.toggleViewAction())
        action(view_menu, "&Reset panel layout", self._reset_panel_layout)
        view_menu.addSeparator()
        action(view_menu, "&Clear graph", self._clear_graph, "Ctrl+R")
        view_menu.addSeparator()
        self.full_screen_action = QAction("&Full screen", self)
        self.full_screen_action.setCheckable(True)
        self.full_screen_action.setShortcut("F11")
        self.full_screen_action.toggled.connect(self._set_full_screen)
        view_menu.addAction(self.full_screen_action)
        self.exit_full_screen_action = QAction(self)
        self.exit_full_screen_action.setShortcut("Esc")
        self.exit_full_screen_action.setEnabled(False)
        self.exit_full_screen_action.triggered.connect(lambda: self.full_screen_action.setChecked(False))
        self.addAction(self.exit_full_screen_action)

        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(self.update_action)
        help_menu.addSeparator()
        action(help_menu, "Recording &guide", self._show_recording_guide, "F1")
        help_menu.addSeparator()
        action(help_menu, "&About Voltmeter", self._show_about)

    def _clear_graph(self):
        # Clear only display history; never touch saved data or its sequence.
        with self._data_lock:
            self._start_ts = None
            self._time_buffer.clear()
            for buffer in self.buffers.values():
                buffer.clear()
            self._plot_revision += 1
            for curve in self.curves.values():
                curve.setData([], [])

    def _refresh_plot_state(self, *_):
        active = (not self._collection_mode and not self._closing
                  and self._chart_presented and not self.isMinimized())
        with self._data_lock:
            changed = active != self._plot_active
            self._plot_active = active
            if changed:
                self._start_ts = None
                self._time_buffer.clear()
                for buffer in self.buffers.values():
                    buffer.clear()
                self._plot_revision += 1
        if changed:
            for curve in self.curves.values():
                curve.setData([], [])
        if not self._collection_mode:
            self.timer.setInterval(100 if active else self._collection_ui_refresh_ms)

    def _on_chart_visibility_changed(self, visible):
        # In a tab group this signal reports the presented tab, unlike isVisible().
        self._chart_presented = visible
        self._refresh_plot_state()

    def _set_collection_mode(self, enabled):
        if enabled and self.acq.recorder is None:
            self.collection_mode_action.blockSignals(True)
            self.collection_mode_action.setChecked(False)
            self.collection_mode_action.blockSignals(False)
            return
        self._collection_mode = enabled
        self.setMinimumHeight(360 if enabled else 740)
        if enabled:
            self._monitor_layout = self.saveState()
            self.display_layout.removeWidget(self.voltage_label)
            self.recording_layout.addWidget(self.voltage_label, 0, 0, 1, 3)
            mode_font = QFont(self.voltage_font)
            mode_font.setPointSize(20)
            self.voltage_label.setFont(mode_font)
            self.measurement_dock.hide()
            self.chart_dock.hide()
            self.recording_dock.show()
            self.recording_dock.raise_()
            self.timer.setInterval(self._collection_ui_refresh_ms)
        elif self._monitor_layout is not None:
            self.recording_layout.removeWidget(self.voltage_label)
            self.display_layout.insertWidget(1, self.voltage_label)
            self.voltage_label.setFont(self.voltage_font)
            self.restoreState(self._monitor_layout)
            self._monitor_layout = None
        self.chart_dock.toggleViewAction().setEnabled(not enabled)
        self.measurement_dock.toggleViewAction().setEnabled(not enabled)
        self.rate_spin.setEnabled(not enabled)
        self.gain_combo.setEnabled(not enabled)
        self.collection_mode_action.setText("Return to live view" if enabled else "Data collection mode")
        self._refresh_plot_state()
        self._update_ui()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "timer"):
            self._refresh_plot_state()

    def _set_full_screen(self, enabled):
        self.exit_full_screen_action.setEnabled(enabled)
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()

    def _show_recording_guide(self):
        QMessageBox.information(self, "Recording guide",
            "Readings are saved automatically to CSV in mV.\n\n"
            "Pause measurement (Ctrl+Space) stops both reading and saving. "
            "Start measurement resumes the current session.\n\n"
            "To change destination, pause first, then choose File > Change recording folder. "
            "A new session starts and existing files are kept. "
            "File > Recording settings sets the maximum data rows per file (header excluded), "
            "daily rotation, filename prefix, CSV columns, minimum free drive space "
            "and storage retry interval. "
            "Remember settings saves these preferences for the next launch. "
            "Reaching a row limit continues in a new file; low disk space pauses new readings "
            "until the pending sample can be saved.\n\n"
            "File > Open recording folder (Ctrl+O) opens the saved files. "
            "Clear graph (Ctrl+R) clears display history only.\n\n"
            "Data collection mode (Ctrl+M) stops graph work and updates status every few seconds. "
            "ADC readings and CSV syncing continue unchanged. Return to live view starts a new graph history.\n\n"
            "Drag a panel title to move it, dock it at an edge, or stack panels as tabs. "
            "Double-click its title to detach or dock it. "
            "View reopens closed panels; Reset panel layout restores the original arrangement. "
            "Closing a panel does not stop measurement or recording.\n\n"
            "MockAdc / SIMULATED DATA means the readings are simulated. "
            "Storage errors pause acquisition and retry the pending sample automatically. "
            "The Save data panel shows retry status.")

    def _show_about(self):
        QMessageBox.about(self, "About Voltmeter",
            f"Voltmeter v{APP_VERSION}\n\nADS1256 differential measurement with live plotting "
            "and automatic CSV recording.\n\n"
            f"Current ADC: {type(self.acq.adc).__name__}\n"
            "Built with Python and PyQt6.")

    def _on_data(self, ts, readings):
        if isinstance(readings, Exception):
            notify = self._last_error is None or self.acq.recording_error is readings
            self._last_error = readings
            self._error_count += 1
            if notify and not self._closing:
                self._error_received.emit()
        else:
            recovered = self._last_error is not None and self.acq.recording_error is None
            self._last = readings
            self._last_error = None
            if recovered and not self._closing:
                self._error_received.emit()
            with self._data_lock:
                if not self._plot_active:
                    return
                if self._start_ts is None:
                    self._start_ts = ts
                rel_ts = ts - self._start_ts
                self._time_buffer.append(rel_ts)
                for ch, v in readings.items():
                    self.buffers.setdefault(
                        ch, deque(maxlen=self._calc_maxlen())
                    ).append(v)
                self._plot_revision += 1

    def _update_ui(self):
        if self._closing:
            return
        self._update_recording_ui()
        source = type(self.acq.adc).__name__
        if source == "MockAdc":
            source += " / SIMULATED DATA"
        mode = "Data collection: graph off" if self._collection_mode else "Live view" if self._plot_active else "Graph inactive"
        self.mode_label.setText(f"{mode} | {source} | Status refresh: {self.timer.interval() / 1000:g} s")
        if self._last_error is not None:
            retrying = self.acq.recording_retrying
            self.voltage_label.setText("STORAGE RETRY" if retrying else "ERROR")
            self.voltage_label.setStyleSheet(
                "color: white; background-color: "
                + ("#9A6700" if retrying else "#C62828")
                + "; padding: 20px; border-radius: 10px; font-weight: bold;")
            self.status_label.setText(f"{self._last_error} (Errors: {self._error_count})")
            self.status_label.setWordWrap(True)
            self.status_label.setStyleSheet("color: #C62828; padding: 4px; font-weight: bold;")
        elif self._collection_mode:
            self.voltage_label.setText("DATA COLLECTION MODE" if self.acq._running else "COLLECTION MODE PAUSED")
            self.voltage_label.setStyleSheet(
                "color: #2E7D32; background-color: #E8F5E9; padding: 12px; border-radius: 10px;")
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
            if not self._plot_active or self._plot_revision == self._last_plot_revision:
                return
            self._last_plot_revision = self._plot_revision
            times = list(self._time_buffer)
            snapshots = {ch: list(self.buffers.get(ch, [])) for ch in self.curves}
        for ch, data in snapshots.items():
            if data and times:
                x, y = self._downsample(times, data)
                self.curves[ch].setData(x, [value * 1000.0 for value in y])

    def _update_recording_ui(self):
        recorder = self.acq.recorder
        retrying = self.acq.recording_retrying
        failed = self.acq.recording_error is not None and not retrying
        running = self.acq._running
        self.start_btn.setEnabled(not failed)
        self.start_btn.setText("Stopped" if failed else "Pause measurement" if running else "Start measurement")
        self.change_folder_btn.setEnabled(recorder is not None and not running and not failed)
        self.open_folder_btn.setEnabled(recorder is not None)
        self.copy_path_btn.setEnabled(recorder is not None and recorder.path is not None)
        self.recording_settings_btn.setEnabled(recorder is not None and not running and not failed)
        self.recording_settings_action.setEnabled(self.recording_settings_btn.isEnabled())
        self.open_folder_action.setEnabled(self.open_folder_btn.isEnabled())
        self.change_folder_action.setEnabled(self.change_folder_btn.isEnabled())
        self.copy_path_action.setEnabled(self.copy_path_btn.isEnabled())
        self.measurement_action.setEnabled(not failed)
        self.collection_mode_action.setEnabled(recorder is not None)
        self.measurement_action.setText("&Pause measurement" if running else "&Start measurement")
        if failed or retrying:
            self.recording_dock.show()
            self.recording_dock.raise_()
        if failed:
            state, color = str(self.acq.recording_error), "#C62828"
        elif retrying:
            state, color = str(self.acq.recording_error) + " | Reading paused until this sample is saved", "#9A6700"
        elif recorder is None:
            state, color = "Saving disabled - measurements are not recorded", "#9A6700"
        elif self.acq.pending_recording is not None:
            state, color = "Paused with one unsaved sample - start measurement to retry", "#9A6700"
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
        if recorder is not None:
            limit = f"{recorder.max_data_lines:,}" if recorder.max_data_lines else "unlimited"
            free = f"{recorder.last_free_bytes / 1024**3:.2f} GiB" if recorder.last_free_bytes is not None else "checked on next reading"
            self.file_info_label.setText(
                f"File rows: {recorder.file_saved_count:,} / {limit} | Files: {recorder.files_created} | "
                f"File size: {recorder.current_file_bytes / 1024:.1f} KiB | Free: {free}")
        else:
            self.file_info_label.setText("No active recording session")
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
            replacement = CsvRecorder(folder, self.acq.channels, self.acq.adc, self.acq.averaging, **recorder.options())
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

    def _show_recording_settings(self):
        recorder = self.acq.recorder
        if recorder is None or self.acq._running or self.acq.recording_error is not None:
            return
        dialog = RecordingSettingsDialog(recorder, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_recording_settings(dialog.recording_options(), dialog.remember.isChecked())

    def _apply_recording_settings(self, options, remember=False):
        recorder = self.acq.recorder
        if recorder is None or self.acq._running or self.acq.recording_error is not None:
            return False
        replacement = None
        try:
            replacement = CsvRecorder(channels=self.acq.channels, adc=self.acq.adc,
                                      averaging=self.acq.averaging, **options)
            if remember:
                saved = dict(options, directory=str(replacement.directory))
                save_recording_settings(saved)
        except Exception as exc:
            if replacement is not None:
                replacement.close()
            QMessageBox.warning(self, "Recording settings", f"Could not apply settings: {exc}")
            return False
        try:
            recorder.close()
        except Exception as exc:
            replacement.close()
            self.acq.recording_error = RuntimeError(f"Recording close failed: {exc}")
            self._update_ui()
            return False
        self.acq.recorder = replacement
        self._update_ui()
        return True

    def _toggle(self):
        if self.acq.recording_error is not None and not self.acq.recording_retrying:
            return
        if self.acq._running:
            self.acq.stop()
            if self._last_error is not None and self.acq.recording_error is None:
                self._last_error = None
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

    def _show_update_dialog(self):
        from gui.update_dialog import UpdateDialog
        UpdateDialog(self).exec()

    def prepare_for_update(self):
        if self.acq.recording_retrying or self.acq.pending_recording is not None:
            self.update_error_detail = "A sample is waiting for storage. Let it save before updating."
            return False
        self._was_running_before_update = self.acq._running
        self.acq.stop()
        worker = getattr(self.acq, "_thread", None)
        if worker is not None and worker.is_alive():
            self.update_error_detail = "The measurement worker is still running."
            return False
        self._recorder_before_update = self.acq.recorder
        try:
            if self._recorder_before_update is not None:
                self._recorder_before_update.close()
        except OSError as exc:
            self.update_error_detail = f"Could not safely close the CSV file: {exc}"
            return False
        self._update_ui()
        return True

    def resume_after_failed_update(self):
        old = self._recorder_before_update
        if old is not None:
            self.acq.recorder = CsvRecorder(
                old.directory, self.acq.channels, self.acq.adc,
                self.acq.averaging, **old.options(),
            )
        if self._was_running_before_update:
            self.acq.start()
        self._update_ui()

    def restart_after_update(self, dialog):
        self.update_requested = True
        dialog.accept()
        self.close()

    def closeEvent(self, event):
        self._closing = True
        self._refresh_plot_state()
        self.timer.stop()
        self.acq.stop()
        if self.acq.recorder is not None:
            self.acq.recorder.close()
        event.accept()
