"""Exercise recording controls on a real offscreen Qt window."""
import csv
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLocale, Qt
from core.acquisition import AcquisitionManager
from core.recording import CsvRecorder
from gui.main_window import MainWindow
from hardware.adc import MockAdc
from gui.recording_settings import RecordingSettingsDialog
from config import load_recording_settings, save_recording_settings


class RecordingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.adc = MockAdc(single_ended=False, gain=64)
        self.recorder = CsvRecorder(self.temp.name, [(0, 1)], self.adc)
        self.acq = AcquisitionManager(self.adc, [(0, 1)], sample_rate=30, recorder=self.recorder)
        self.win = MainWindow(self.acq)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.win.close)

    def wait_for_saved(self, minimum=1):
        deadline = time.monotonic() + 3
        while self.acq.recorder.saved_count < minimum and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertGreaterEqual(self.acq.recorder.saved_count, minimum)
        self.win._update_ui()

    def test_pause_resume_copy_and_folder_change_preserve_data(self):
        self.win._update_ui()
        self.assertIn("SIMULATED DATA", self.win.source_label.text())
        self.win.start_btn.click()
        self.wait_for_saved(2)
        self.assertFalse(self.win.change_folder_btn.isEnabled())
        self.win.copy_path_btn.click()
        self.assertEqual(self.app.clipboard().text(), str(self.recorder.path))
        with patch("gui.main_window.QDesktopServices.openUrl", return_value=True) as open_url:
            self.win.open_folder_btn.click()
            self.assertEqual(Path(open_url.call_args[0][0].toLocalFile()), self.recorder.directory)
        self.win.start_btn.click()
        self.assertFalse(self.acq._running)
        count = self.recorder.saved_count
        first_path = self.recorder.path
        self.win._update_ui()
        self.assertIn("Paused", self.win.recording_label.text())
        self.assertEqual(self.recorder.saved_count, count)
        self.win.start_btn.click()
        self.wait_for_saved(count + 1)
        self.win.start_btn.click()
        self.assertEqual(self.recorder.path, first_path)
        original = first_path.read_bytes()
        destination = Path(self.temp.name) / "new folder"
        with patch("gui.main_window.QFileDialog.getExistingDirectory", return_value=str(destination)):
            self.win.change_folder_btn.click()
        self.assertEqual(self.acq.recorder.directory, destination)
        self.assertEqual(self.acq.recorder.saved_count, 0)
        self.win.start_btn.click()
        self.wait_for_saved()
        self.win.start_btn.click()
        self.assertEqual(first_path.read_bytes(), original)
        with self.acq.recorder.path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), self.acq.recorder.saved_count)
        self.assertEqual(rows[0]["sequence"], "1")

    def test_write_error_stays_visible_and_cannot_resume(self):
        with patch.object(self.recorder, "write", side_effect=OSError("disk full")):
            self.win.start_btn.click()
            self.acq._thread.join(timeout=3)
        self.win._update_ui()
        self.assertIn("disk full", self.win.recording_label.text())
        self.assertFalse(self.win.start_btn.isEnabled())
        self.assertFalse(self.win.change_folder_btn.isEnabled())
        self.assertEqual(self.recorder.saved_count, 0)
        self.assertIsNone(self.recorder.last_saved_timestamp)

    def test_cancel_or_invalid_folder_keeps_current_session(self):
        self.win._update_ui()
        with patch("gui.main_window.QFileDialog.getExistingDirectory", return_value=""):
            self.win.change_folder_btn.click()
        self.assertIs(self.acq.recorder, self.recorder)
        blocked = Path(self.temp.name) / "file"
        blocked.write_text("keep")
        with patch("gui.main_window.QFileDialog.getExistingDirectory", return_value=str(blocked)), \
             patch("gui.main_window.QMessageBox.warning") as warning:
            self.win.change_folder_btn.click()
        warning.assert_called_once()
        self.assertIs(self.acq.recorder, self.recorder)
        self.assertEqual(blocked.read_text(), "keep")

    def test_movable_panels_preserve_recording_and_reset_layout(self):
        self.win.show()
        self.app.processEvents()
        self.assertEqual([a.text() for a in self.win.menuBar().actions()], ["&File", "&View", "&Help"])
        self.win.measurement_action.trigger()
        self.wait_for_saved(2)
        self.win.recording_dock.setFloating(True)
        self.assertTrue(self.win.recording_dock.isFloating())
        self.win.recording_dock.close()
        count = self.recorder.saved_count
        self.wait_for_saved(count + 1)
        self.assertTrue(self.acq._running)
        self.win.recording_dock.setFloating(False)
        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.win.recording_dock)
        self.win.recording_dock.show()
        self.app.processEvents()
        self.win.tabifyDockWidget(self.win.measurement_dock, self.win.recording_dock)
        self.assertIn(self.win.recording_dock, self.win.tabifiedDockWidgets(self.win.measurement_dock))
        self.win._reset_panel_layout()
        self.app.processEvents()
        for dock in (self.win.measurement_dock, self.win.recording_dock, self.win.chart_dock):
            self.assertFalse(dock.isFloating())
            self.assertFalse(dock.isHidden())
        self.assertFalse(self.win.tabifiedDockWidgets(self.win.measurement_dock))
        self.win.measurement_action.trigger()
        with self.recorder.path.open(newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), self.recorder.saved_count)

    def test_recording_error_reopens_closed_recording_dock(self):
        self.win.show()
        self.win.recording_dock.close()
        self.assertTrue(self.win.recording_dock.isHidden())
        self.acq.recording_error = RuntimeError("disk full")
        self.win._update_ui()
        self.assertFalse(self.win.recording_dock.isHidden())
        self.assertFalse(self.win.measurement_action.isEnabled())

    def test_settings_apply_remember_and_rotation_preserve_old_session(self):
        self.win.start_btn.click()
        self.wait_for_saved(2)
        self.assertFalse(self.win.recording_settings_action.isEnabled())
        self.win.start_btn.click()
        original_path = self.recorder.path
        original = original_path.read_bytes()
        dialog = RecordingSettingsDialog(self.recorder, self.win)
        dialog.max_lines.setValue(2)
        dialog.prefix.setText("new_test")
        dialog.daily.setChecked(False)
        preferences = Path(self.temp.name) / "settings.json"
        with patch("gui.main_window.RecordingSettingsDialog", return_value=dialog), \
             patch.object(dialog, "exec", return_value=dialog.DialogCode.Accepted), \
             patch("gui.main_window.save_recording_settings", side_effect=lambda opts: save_recording_settings(opts, preferences)):
            self.win.recording_settings_action.trigger()
        self.assertEqual(load_recording_settings(preferences)["max_data_lines"], 2)
        self.assertEqual(self.acq.recorder.saved_count, 0)
        self.win.start_btn.click()
        self.wait_for_saved(5)
        self.win.start_btn.click()
        files = sorted(Path(self.temp.name).glob("new_test_*.csv"))
        counts = []
        for path in files:
            with path.open(newline="") as handle:
                counts.append(len(list(csv.DictReader(handle))))
        self.assertTrue(all(0 < count <= 2 for count in counts))
        self.assertEqual(sum(counts), self.acq.recorder.saved_count)
        self.assertEqual(original_path.read_bytes(), original)
        self.assertIn("/ 2", self.win.file_info_label.text())

    def test_failed_preference_save_keeps_current_session(self):
        options = dict(self.recorder.options(), directory=self.temp.name)
        with patch("gui.main_window.save_recording_settings", side_effect=OSError("read only")), \
             patch("gui.main_window.QMessageBox.warning") as warning:
            self.assertFalse(self.win._apply_recording_settings(options, remember=True))
        self.assertIs(self.acq.recorder, self.recorder)
        warning.assert_called_once()

    def test_numeric_controls_use_ascii_digits_under_arabic_system_locale(self):
        previous = QLocale()
        QLocale.setDefault(QLocale("ar_EG"))
        other = None
        try:
            other = MainWindow(self.acq)
            other.rate_spin.setValue(1234)
            self.assertEqual(other.rate_spin.cleanText(), "1,234")
            dialog = RecordingSettingsDialog(self.recorder, other)
            dialog.max_lines.setValue(123456)
            dialog.min_free.setValue(5678)
            self.assertEqual(dialog.max_lines.cleanText(), "123,456")
            self.assertEqual(dialog.min_free.cleanText(), "5,678")
            self.assertEqual(dialog.min_free.suffix(), "")
            dialog.max_lines.lineEdit().setText("234,567")
            dialog.max_lines.interpretText()
            self.assertEqual(dialog.recording_options()["max_data_lines"], 234567)
            self.assertEqual(other.locale().zeroDigit(), "0")
            dialog.close()
        finally:
            if other is not None:
                other.close()
            QLocale.setDefault(previous)

    def test_collection_mode_stops_graph_work_without_losing_csv_rows(self):
        self.win.show()
        self.app.processEvents()
        self.win.start_btn.click()
        self.wait_for_saved(2)
        self.assertTrue(self.win._time_buffer)
        rate, gain = self.acq.sample_rate, self.adc.gain
        path = self.recorder.path
        self.win.collection_mode_action.trigger()
        self.assertTrue(self.win._collection_mode)
        self.assertEqual(self.win.timer.interval(), 3000)
        self.assertFalse(self.win._plot_active)
        self.assertFalse(self.win._time_buffer)
        self.assertTrue(self.win.chart_dock.isHidden())
        count = self.recorder.saved_count
        curve = self.win.curves[(0, 1)]
        with patch.object(curve, "setData", wraps=curve.setData) as draw, \
             patch.object(self.win, "_downsample", wraps=self.win._downsample) as downsample:
            self.wait_for_saved(count + 5)
            self.win._update_ui()
            draw.assert_not_called()
            downsample.assert_not_called()
        self.assertFalse(self.win._time_buffer)
        self.assertEqual(self.acq.sample_rate, rate)
        self.assertEqual(self.adc.gain, gain)
        self.assertIs(self.acq.recorder, self.recorder)
        self.win.collection_mode_action.trigger()
        self.app.processEvents()
        self.assertTrue(self.win._plot_active)
        self.assertEqual(self.win.timer.interval(), 100)
        count = self.recorder.saved_count
        self.wait_for_saved(count + 2)
        self.win.measurement_action.trigger()
        self.assertTrue(self.win._time_buffer)
        self.assertLess(self.win._time_buffer[0], 0.01)
        self.assertEqual(self.recorder.path, path)
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([int(row["sequence"]) for row in rows], list(range(1, self.recorder.saved_count + 1)))

    def test_reset_layout_preserves_collection_mode_and_recording(self):
        self.win.show()
        self.app.processEvents()
        self.win.measurement_action.trigger()
        self.wait_for_saved(2)
        path = self.recorder.path
        self.win.collection_mode_action.trigger()
        self.win.recording_dock.setFloating(True)
        self.win.recording_dock.close()
        view_menu = self.win.menuBar().actions()[1].menu()
        reset_action = next(action for action in view_menu.actions()
                            if action.text() == "&Reset panel layout")
        reset_action.trigger()
        self.app.processEvents()
        self.assertTrue(self.win._collection_mode)
        self.assertTrue(self.win.collection_mode_action.isChecked())
        self.assertEqual(self.win.timer.interval(), 3000)
        self.assertFalse(self.win._plot_active)
        self.assertTrue(self.win.measurement_dock.isHidden())
        self.assertTrue(self.win.chart_dock.isHidden())
        self.assertFalse(self.win.recording_dock.isHidden())
        self.assertFalse(self.win.recording_dock.isFloating())
        self.assertTrue(self.acq._running)
        self.assertIs(self.acq.recorder, self.recorder)
        self.wait_for_saved(self.recorder.saved_count + 3)
        self.assertFalse(self.win._time_buffer)
        self.assertEqual(self.recorder.path, path)
        self.win.collection_mode_action.trigger()
        self.app.processEvents()
        for dock in (self.win.measurement_dock, self.win.recording_dock, self.win.chart_dock):
            self.assertFalse(dock.isHidden())
            self.assertFalse(dock.isFloating())
        self.win.measurement_action.trigger()
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([int(row["sequence"]) for row in rows],
                         list(range(1, self.recorder.saved_count + 1)))

    def test_hidden_and_minimized_graph_skip_work_and_restore(self):
        self.win.show()
        self.app.processEvents()
        self.assertTrue(self.win._plot_active)
        self.win.chart_dock.close()
        self.app.processEvents()
        self.assertFalse(self.win._plot_active)
        self.win._on_data(time.time(), {(0, 1): 0.01})
        self.assertFalse(self.win._time_buffer)
        self.assertEqual(self.win.timer.interval(), 3000)
        self.win.chart_dock.show()
        self.app.processEvents()
        self.assertTrue(self.win._plot_active)
        self.win.showMinimized()
        self.app.processEvents()
        self.assertFalse(self.win._plot_active)
        self.win.showNormal()
        self.app.processEvents()
        self.assertTrue(self.win._plot_active)
        self.win.tabifyDockWidget(self.win.recording_dock, self.win.chart_dock)
        self.win.recording_dock.raise_()
        self.app.processEvents()
        self.assertFalse(self.win._plot_active)
        self.win.chart_dock.raise_()
        self.app.processEvents()
        self.assertTrue(self.win._plot_active)

    def test_collection_mode_reports_storage_failure_without_waiting_for_timer(self):
        self.win.show()
        self.win.collection_mode_action.trigger()
        with patch.object(self.recorder, "write", side_effect=OSError("disk full")):
            self.win.measurement_action.trigger()
            self.acq._thread.join(timeout=2)
        # Process the queued error signal; do not manually refresh or wait 3s.
        self.app.processEvents()
        self.assertIn("disk full", self.win.recording_label.text())
        self.assertFalse(self.win.measurement_action.isEnabled())
        self.assertFalse(self.acq._running)

    def test_collection_mode_can_be_enabled_on_startup(self):
        other = MainWindow(self.acq, collection_mode=True)
        try:
            other.show()
            self.app.processEvents()
            self.assertTrue(other._collection_mode)
            self.assertFalse(other._plot_active)
            self.assertEqual(other.timer.interval(), 3000)
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
