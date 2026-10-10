import csv
from datetime import datetime, timedelta
import errno
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from core.acquisition import AcquisitionManager
from core.recording import CsvRecorder
from hardware.adc import MockAdc
from config import load_recording_settings, save_recording_settings


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.adc = MockAdc(single_ended=False, gain=64)
        self.recorder = CsvRecorder(self.temp.name, [(0, 1)], self.adc)
        self.addCleanup(self.recorder.close)

    def rows(self, path):
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_synced_rows_visible_before_close_and_daily_rotation(self):
        now = datetime.now().replace(hour=12, minute=0)
        with patch("core.recording.os.fsync", wraps=__import__("os").fsync) as sync:
            self.recorder.write(now.timestamp(), {(0, 1): 0.0123456789})
            self.assertGreaterEqual(sync.call_count, 2)  # header and row
        first = self.recorder.path
        row = self.rows(first)[0]
        self.assertEqual(row["AD0-AD1_mV"], "12.3456789")
        self.assertEqual(row["adc_source"], "MockAdc")
        self.assertEqual(row["input_mode"], "differential")
        self.recorder.write((now + timedelta(days=1)).timestamp(), {(0, 1): -0.01})
        self.assertNotEqual(first, self.recorder.path)
        self.assertEqual(len(self.rows(first)), 1)
        self.assertEqual(self.rows(self.recorder.path)[0]["sequence"], "2")

    def test_new_session_does_not_overwrite(self):
        self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.01})
        first = self.recorder.path
        original = first.read_bytes()
        other = CsvRecorder(self.temp.name, [(0, 1)], self.adc)
        try:
            other.write(datetime.now().timestamp(), {(0, 1): 0.02})
            self.assertNotEqual(first, other.path)
            self.assertEqual(first.read_bytes(), original)
        finally:
            other.close()

    def test_sync_failure_not_counted_and_not_retried_silently(self):
        self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.01})
        with patch("core.recording.os.fsync", side_effect=OSError(errno.ENOSPC, "disk full")):
            with self.assertRaises(OSError):
                self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.02})
        self.assertEqual(self.recorder.saved_count, 1)
        with self.assertRaises(RuntimeError):
            self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.03})

    def test_acquisition_stops_and_reports_storage_failure(self):
        delivered = []
        acq = AcquisitionManager(self.adc, [(0, 1)], sample_rate=100, recorder=self.recorder)
        acq.add_callback(lambda ts, data: delivered.append(data))
        with patch.object(self.recorder, "write", side_effect=OSError("disk full")):
            acq.start()
            acq._thread.join(timeout=2)
            acq.stop()
        self.assertFalse(acq._running)
        self.assertEqual(len(delivered), 1)
        self.assertIsInstance(delivered[0], Exception)
        with self.assertRaises(RuntimeError):
            acq.start()

    def test_stop_waits_for_inflight_recording(self):
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        actual_write = self.recorder.write

        def slow_write(ts, readings):
            entered.set()
            release.wait(3)
            actual_write(ts, readings)

        acq = AcquisitionManager(self.adc, [(0, 1)], recorder=self.recorder)
        with patch.object(self.recorder, "write", side_effect=slow_write):
            acq.start()
            self.assertTrue(entered.wait(2))
            stopper = threading.Thread(target=lambda: (acq.stop(), stopped.set()))
            stopper.start()
            try:
                self.assertFalse(stopped.wait(0.05))
            finally:
                release.set()
                stopper.join(timeout=3)
                acq.stop()
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.recorder.saved_count, 1)

    def test_terminal_records_five_rows(self):
        result = subprocess.run(
            [sys.executable, "-B", "serial_monitor.py", "--mock", "--rate", "100",
             "--count", "5", "--quiet", "--log-dir", self.temp.name],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        files = list(Path(self.temp.name).glob("*.csv"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(self.rows(files[0])), 5)

    def test_terminal_exits_on_invalid_storage(self):
        blocked = Path(self.temp.name) / "not_a_directory"
        blocked.write_text("existing file")
        result = subprocess.run(
            [sys.executable, "-B", "serial_monitor.py", "--mock", "--count", "5",
             "--log-dir", str(blocked)], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("recording failed", result.stderr)
        self.assertEqual(blocked.read_text(), "existing file")

    def test_synced_rows_survive_forced_process_termination(self):
        # Process termination tests buffering, not physical power-cut resilience.
        process = subprocess.Popen(
            [sys.executable, "-B", "serial_monitor.py", "--mock", "--rate", "30",
             "--quiet", "--log-dir", self.temp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            before = []
            while time.monotonic() < deadline:
                files = list(Path(self.temp.name).glob("*.csv"))
                if files:
                    before = self.rows(files[0])
                    if len(before) >= 3:
                        break
                time.sleep(0.02)
            self.assertGreaterEqual(len(before), 3)
            process.kill()
            process.wait(timeout=5)
            after = self.rows(files[0])
            self.assertEqual(after[:len(before)], before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_line_limit_rotates_without_gaps_or_empty_trailing_file(self):
        recorder = CsvRecorder(self.temp.name, [(0, 1)], self.adc, max_data_lines=2, file_prefix="site_1")
        self.addCleanup(recorder.close)
        now = datetime.now().timestamp()
        for i in range(5):
            recorder.write(now + i, {(0, 1): i / 1000})
        files = sorted(Path(self.temp.name).glob("site_1_*.csv"))
        batches = [self.rows(path) for path in files]
        self.assertEqual([len(rows) for rows in batches], [2, 2, 1])
        self.assertEqual([int(row["sequence"]) for rows in batches for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual(recorder.saved_count, 5)
        self.assertEqual(recorder.file_saved_count, 1)
        self.assertEqual(recorder.files_created, 3)
        self.assertEqual(recorder.current_file_bytes, recorder.path.stat().st_size)

    def test_disabled_daily_rotation_and_zero_line_limit(self):
        recorder = CsvRecorder(self.temp.name, [(0, 1)], self.adc, max_data_lines=0, rotate_daily=False)
        self.addCleanup(recorder.close)
        now = datetime.now().replace(hour=12).timestamp()
        recorder.write(now, {(0, 1): 0.01})
        first = recorder.path
        recorder.write(now + 86400, {(0, 1): 0.02})
        self.assertEqual(recorder.path, first)
        self.assertEqual(recorder.files_created, 1)
        self.assertEqual(len(self.rows(first)), 2)

    def test_daily_and_line_limit_boundary_creates_only_one_new_file(self):
        recorder = CsvRecorder(self.temp.name, [(0, 1)], self.adc, max_data_lines=1)
        self.addCleanup(recorder.close)
        now = datetime.now().replace(hour=12).timestamp()
        recorder.write(now, {(0, 1): 0.01})
        recorder.write(now + 86400, {(0, 1): 0.02})
        self.assertEqual(recorder.files_created, 2)

    def test_low_space_stops_before_next_write_and_preserves_files(self):
        self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.01})
        original = self.recorder.path.read_bytes()
        self.recorder._next_space_check = 0
        from collections import namedtuple
        usage = namedtuple("Usage", "total used free")(1000, 999, 1)
        with patch("core.recording.shutil.disk_usage", return_value=usage):
            with self.assertRaisesRegex(OSError, "Low disk space"):
                self.recorder.write(datetime.now().timestamp(), {(0, 1): 0.02})
        self.assertEqual(self.recorder.saved_count, 1)
        self.assertEqual(self.recorder.path.read_bytes(), original)

    def test_invalid_options_rejected(self):
        for options in ({"max_data_lines": -1}, {"max_data_lines": 1.5},
                        {"file_prefix": "../escape"}, {"file_prefix": ""},
                        {"min_free_mb": -1}, {"rotate_daily": "false"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                CsvRecorder(self.temp.name, [(0, 1)], self.adc, **options)

    def test_preferences_roundtrip_and_failed_replace_keeps_previous(self):
        path = Path(self.temp.name) / "preferences.json"
        settings = dict(self.recorder.options(), directory=str(self.recorder.directory))
        save_recording_settings(settings, path)
        self.assertEqual(load_recording_settings(path), settings)
        original = path.read_bytes()
        with patch("config.os.replace", side_effect=OSError("permission denied")):
            with self.assertRaises(OSError):
                save_recording_settings(dict(settings, max_data_lines=1), path)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(list(Path(self.temp.name).glob(".recording_settings_*.tmp")))

    def test_terminal_line_limit_rotates(self):
        result = subprocess.run(
            [sys.executable, "-B", "serial_monitor.py", "--mock", "--rate", "100",
             "--count", "5", "--max-data-lines", "2", "--file-prefix", "cli",
             "--quiet", "--log-dir", self.temp.name], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        batches = [self.rows(path) for path in sorted(Path(self.temp.name).glob("cli_*.csv"))]
        self.assertEqual([len(rows) for rows in batches], [2, 2, 1])


if __name__ == "__main__":
    unittest.main()
