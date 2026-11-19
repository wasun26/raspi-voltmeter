import csv
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock

from core.auto_gain import AutoGain, GainConfigurationError, read_scan
from core.recording import CsvRecorder
from hardware.adc import ADS1256, MockAdc
from config import load_gain_settings, save_gain_settings


class AutoGainTests(unittest.TestCase):
    def test_gain_preference_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gain_settings.json"
            save_gain_settings(None, path)
            self.assertEqual(load_gain_settings(path), {"auto": True, "gain": 1})
            save_gain_settings(32, path)
            self.assertEqual(load_gain_settings(path), {"auto": False, "gain": 32})

    def adc(self, gain=1):
        return MockAdc(gain=gain, single_ended=False, sample_rate=0,
                       error_mode="stuck", offset=0)

    def test_quiet_increases_one_step_after_dwell_and_high_reduces(self):
        adc = self.adc()
        auto = AutoGain(enabled=True)
        auto.begin_scan(adc, 0)
        auto.observe(1, 0.1, False, 0)
        auto.observe(1, 0.1, False, 9)
        self.assertIsNone(auto.pending)
        auto.observe(1, 0.1, False, 10)
        auto.begin_scan(adc, 10)
        self.assertEqual(adc.gain, 2)
        auto.observe(2, 0.85, False, 10.1)
        auto.begin_scan(adc, 10.2)
        self.assertEqual(adc.gain, 1)

    def test_clipped_positive_and_negative_jump_to_minimum(self):
        for voltage in (1, -1):
            adc = self.adc(64)
            adc.offset = voltage
            auto = AutoGain(enabled=True)
            auto.pending = None
            scan = read_scan(adc, [(0, 1)], 1, auto)
            self.assertEqual(scan.metadata["clipped"], 1)
            self.assertEqual(auto.pending, 1)
            self.assertEqual(scan.metadata["gain"], 64)
            read_scan(adc, [(0, 1)], 1, auto)
            self.assertEqual(adc.gain, 1)

    def test_clipping_checked_before_averaging_and_across_channels(self):
        adc = self.adc(64)
        values = iter([0, 0, 1, -1])
        adc._generate_sample = lambda: next(values)
        adc.error_mode = "normal"
        auto = AutoGain(enabled=True)
        auto.pending = None
        scan = read_scan(adc, [(0, 1), (2, 3)], 2, auto)
        self.assertEqual(scan[(2, 3)], 0)
        self.assertEqual(scan.metadata["channels"][(0, 1)]["clipped"], 0)
        self.assertEqual(scan.metadata["channels"][(2, 3)]["clipped"], 1)
        self.assertEqual(auto.pending, 1)
        self.assertEqual(len(json.loads(scan.metadata["channels"][(2, 3)]["raw_counts"])), 2)

    def test_pause_resets_dwell_and_cancels_increase(self):
        auto = AutoGain(enabled=True)
        auto.pending = None
        auto.observe(1, 0, False, 0)
        auto.observe(1, 0, False, 10)
        self.assertEqual(auto.pending, 2)
        auto.reset_quiet()
        self.assertIsNone(auto.pending)
        auto.observe(1, 0, False, 100)
        self.assertIsNone(auto.pending)

    def test_limits_hysteresis_and_latest_manual_request(self):
        auto = AutoGain(enabled=True, min_gain=2, max_gain=8)
        adc = self.adc()
        auto.begin_scan(adc, 0)
        auto.observe(2, 1, True, 1)
        self.assertIsNone(auto.pending)
        auto.observe(2, 0.1, False, 2)
        auto.observe(2, 0.3, False, 11)
        auto.observe(2, 0.1, False, 12)
        self.assertIsNone(auto.pending)
        auto.request_mode(None)
        auto.request_mode(32)
        auto.begin_scan(adc, 13)
        self.assertFalse(auto.enabled)
        self.assertEqual(adc.gain, 32)
        auto.observe(32, 1, True, 14)
        self.assertIsNone(auto.pending)

    def test_capture_metadata_survives_gain_change_and_hidden_columns(self):
        adc = self.adc(64)
        adc.offset = 1
        auto = AutoGain(enabled=True)
        auto.pending = None
        captured = read_scan(adc, [(0, 1)], 1, auto)
        read_scan(adc, [(0, 1)], 1, auto)
        self.assertEqual(adc.gain, 1)
        with tempfile.TemporaryDirectory() as directory:
            recorder = CsvRecorder(directory, [(0, 1)], adc,
                                   included_columns=["timestamp", "AD0-AD1_mV"])
            try:
                recorder.write(time.time(), captured)
                with recorder.path.open(encoding="utf-8", newline="") as handle:
                    row = next(csv.DictReader(handle))
                self.assertEqual(row["gain"], "64")
                self.assertEqual(row["clipped"], "1")
                self.assertEqual(row["AD0-AD1_raw_count"], "8388607")
            finally:
                recorder.close()

    def test_gain_failure_stops_scan_before_any_conversion(self):
        adc = self.adc(64)
        adc.set_gain = Mock(side_effect=IOError("DRDY timeout"))
        adc.read_voltage = Mock()
        with self.assertRaises(GainConfigurationError):
            read_scan(adc, [(0, 1)], 1, AutoGain(enabled=True))
        adc.read_voltage.assert_not_called()

    def test_storage_retry_keeps_capture_gain_and_conversion_timestamps(self):
        adc = self.adc(64)
        adc.offset = 0.01
        auto = AutoGain(enabled=True)
        auto.pending = None
        captured = read_scan(adc, [(0, 1)], 1, auto)
        with tempfile.TemporaryDirectory() as directory:
            recorder = CsvRecorder(directory, [(0, 1)], adc)
            original_write = recorder.write
            attempts = []

            def fail_once(timestamp, readings, captured_monotonic=None):
                attempts.append(readings)
                if len(attempts) == 1:
                    adc.set_gain(1)
                    raise OSError("drive unavailable")
                return original_write(timestamp, readings, captured_monotonic)

            recorder.write = fail_once
            stop = Mock(spec=threading.Event)
            stop.is_set.return_value = False
            stop.wait.return_value = False
            try:
                self.assertTrue(recorder.write_with_retry(time.time(), captured, stop))
                with recorder.path.open(encoding="utf-8", newline="") as handle:
                    row = next(csv.DictReader(handle))
                self.assertEqual(row["gain"], "64")
                self.assertEqual(json.loads(row["AD0-AD1_conversion_unix_s"]),
                                 json.loads(captured.metadata["channels"][(0, 1)]["conversion_unix_s"]))
                self.assertIs(attempts[0], attempts[1])
            finally:
                recorder.close()

    def test_real_driver_waits_and_preserves_other_register_bits(self):
        adc = ADS1256.__new__(ADS1256)
        adc.gain = 64
        adc._wait_drdy = Mock()
        adc._read_reg = Mock(side_effect=[0xA6, 0xA0])
        adc._write_reg = Mock()
        adc.set_gain(1)
        self.assertEqual(adc.gain, 1)
        adc._write_reg.assert_called_once_with(adc.REG_ADCON, 0xA0)
        self.assertEqual(adc._wait_drdy.call_count, 2)

    def test_register_failure_does_not_publish_new_gain(self):
        adc = ADS1256.__new__(ADS1256)
        adc.gain = 64
        adc._wait_drdy = Mock()
        adc._read_reg = Mock(return_value=6)
        adc._write_reg = Mock()
        with self.assertRaises(IOError):
            adc.set_gain(1)
        self.assertEqual(adc.gain, 64)


if __name__ == "__main__":
    unittest.main()
