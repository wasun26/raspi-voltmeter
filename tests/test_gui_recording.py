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
from PyQt6.QtCore import Qt
from core.acquisition import AcquisitionManager
from core.recording import CsvRecorder
from gui.main_window import MainWindow
from hardware.adc import MockAdc


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


if __name__ == "__main__":
    unittest.main()
