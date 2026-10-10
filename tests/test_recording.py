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


if __name__ == "__main__":
    unittest.main()
