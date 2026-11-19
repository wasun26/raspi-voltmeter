"""Durable, daily CSV recording without a growing in-memory backlog."""
import csv
from datetime import datetime
import os
import re
import shutil
from pathlib import Path
import time


def channel_name(channel):
    if isinstance(channel, (tuple, list)) and len(channel) == 2:
        return f"AD{channel[0]}-AD{channel[1]}"
    return f"CH{channel}"


METADATA_COLUMNS = (
    "timestamp", "unix_timestamp", "elapsed_s", "sequence", "adc_source",
    "input_mode", "gain", "vref_V", "averaging", "gain_mode", "gain_event",
    "gain_change_s", "adc_data_rate_SPS", "clipped", "peak_fraction",
)

CHANNEL_CAPTURE_FIELDS = (
    "conversion_start_unix_s", "conversion_end_unix_s", "raw_count",
    "raw_min", "raw_max", "peak_fraction", "clipped",
    "raw_counts", "conversion_unix_s",
)


def sync_directory(directory):
    if os.name == "posix":
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class CsvRecorder:
    """A write succeeds only after flush/fsync; failures propagate to the caller.

    Each session/day gets an exclusively created file. Previously committed files
    are never reopened or overwritten. Storage hardware must honor sync requests.
    """

    def __init__(self, directory, channels, adc, averaging=1, max_data_lines=100000,
                 file_prefix="voltmeter", rotate_daily=True, min_free_mb=100,
                 included_columns=None, retry_interval_sec=5):
        if isinstance(max_data_lines, bool) or not isinstance(max_data_lines, int) or max_data_lines < 0:
            raise ValueError("Max data lines must be a nonnegative integer")
        if not isinstance(file_prefix, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", file_prefix):
            raise ValueError("File prefix: 1-64 letters, numbers, underscores or hyphens; start with a letter or number")
        if not isinstance(rotate_daily, bool):
            raise ValueError("Daily rotation must be true or false")
        if isinstance(min_free_mb, bool) or not isinstance(min_free_mb, int) or min_free_mb < 0:
            raise ValueError("Minimum free MB must be a nonnegative integer")
        if (isinstance(retry_interval_sec, bool) or not isinstance(retry_interval_sec, int)
                or not 1 <= retry_interval_sec <= 3600):
            raise ValueError("Retry interval must be 1-3600 seconds")
        self.max_data_lines = max_data_lines
        self.file_prefix = file_prefix
        self.rotate_daily = rotate_daily
        self.min_free_mb = min_free_mb
        self.retry_interval_sec = retry_interval_sec
        self.directory = Path(directory).expanduser().resolve()
        missing = []
        current = self.directory
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir(exist_ok=True)
            sync_directory(directory.parent)
        if not self.directory.is_dir():
            raise NotADirectoryError(str(self.directory))
        self.channels = tuple(channels)
        channel_columns = tuple(f"{channel_name(ch)}_mV" for ch in self.channels)
        capture_columns = tuple(f"{channel_name(ch)}_{field}" for ch in self.channels
                                for field in CHANNEL_CAPTURE_FIELDS)
        available = METADATA_COLUMNS + channel_columns + capture_columns
        if len(set(available)) != len(available):
            raise ValueError("CSV column names must be unique")
        if included_columns is None:
            included_columns = available
        if (not isinstance(included_columns, (list, tuple))
                or any(not isinstance(column, str) for column in included_columns)
                or len(set(included_columns)) != len(included_columns)
                or "timestamp" not in included_columns
                or not any(column in included_columns for column in channel_columns)
                or any(column not in available for column in included_columns)):
            raise ValueError("Select timestamp and at least one voltage channel; use available CSV columns only")
        self.available_columns = available
        self.included_columns = tuple(column for column in available if column in included_columns)
        self.adc = adc
        self.averaging = averaging
        self.path = None
        self._file = None
        self._writer = None
        self._day = None
        self._part = 0
        self._start = time.monotonic()
        self.saved_count = 0
        self.file_saved_count = 0
        self.files_created = 0
        self.current_file_bytes = 0
        self.last_free_bytes = None
        self._next_space_check = 0.0
        self.last_saved_timestamp = None
        self.error = None

    def _sync(self):
        self._file.flush()
        os.fsync(self._file.fileno())

    def _open(self, when):
        self.close()
        stamp = when.strftime("%Y%m%d_%H%M%S")
        while True:
            self._part += 1
            path = self.directory / f"{self.file_prefix}_{stamp}_{self._part:04d}.csv"
            try:
                handle = path.open("x", newline="", encoding="utf-8")
            except FileExistsError:
                # Same-second restarts/concurrent recorders must never overwrite.
                continue
            self.path = path
            self._file = handle
            break
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.included_columns)
        self._sync()
        # fsync(file) alone does not persist its new directory entry on Linux.
        sync_directory(self.directory)
        self._day = when.strftime("%Y%m%d")
        self.file_saved_count = 0
        self.files_created += 1
        self.current_file_bytes = self._file.tell()

    def options(self):
        return dict(max_data_lines=self.max_data_lines, file_prefix=self.file_prefix,
                    rotate_daily=self.rotate_daily, min_free_mb=self.min_free_mb,
                    included_columns=list(self.included_columns),
                    retry_interval_sec=self.retry_interval_sec)

    def recover(self):
        """Abandon a file with an unconfirmed row; retry in a new file.

        An fsync error leaves that last row's durability unknown. The old file
        is preserved, and the caller retries the same sample with its sequence.
        """
        if self.error is None:
            return
        if not isinstance(self.error, OSError):
            raise RuntimeError(f"Recording cannot be recovered automatically: {self.error}")
        self.close()
        self.error = None
        self._day = None
        self._next_space_check = 0.0

    def write_with_retry(self, timestamp, readings, stop_event, on_retry=None,
                         captured_monotonic=None):
        """Retry one pending sample without acquiring or buffering later samples."""
        retrying = False
        if captured_monotonic is None:
            captured_monotonic = time.monotonic()
        while not stop_event.is_set():
            try:
                self.recover()
                self.write(timestamp, readings, captured_monotonic=captured_monotonic)
            except OSError as exc:
                retrying = True
                if on_retry is not None:
                    on_retry(exc)
                if stop_event.wait(self.retry_interval_sec):
                    break
            else:
                if retrying and on_retry is not None:
                    on_retry(None)
                return True
        return False

    def _check_space(self):
        now = time.monotonic()
        if now >= self._next_space_check:
            self.last_free_bytes = shutil.disk_usage(self.directory).free
            if self.last_free_bytes < self.min_free_mb * 1024 * 1024:
                raise OSError(f"Low disk space: {self.last_free_bytes / 1024 / 1024:.1f} MiB free; "
                              f"minimum is {self.min_free_mb} MiB. Existing files are kept.")
            self._next_space_check = now + 5.0

    def write(self, timestamp, readings, captured_monotonic=None):
        if self.error is not None:
            raise RuntimeError(f"Recording previously failed: {self.error}")
        try:
            metadata = getattr(readings, "metadata", {})
            if metadata.get("gain_mode") == "auto":
                # Keep gain and capture flags even if an old preference hid them.
                required = set(METADATA_COLUMNS[6:])
                required.update(f"{channel_name(ch)}_{field}" for ch in self.channels
                                for field in CHANNEL_CAPTURE_FIELDS)
                columns = tuple(c for c in self.available_columns
                                if c in self.included_columns or c in required)
                if columns != self.included_columns:
                    self.close()  # New schema always starts a new CSV file.
                    self.included_columns = columns
            self._check_space()
            when = datetime.fromtimestamp(timestamp).astimezone()
            day = when.strftime("%Y%m%d")
            if (self._file is None or (self.rotate_daily and self._day != day)
                    or (self.max_data_lines and self.file_saved_count >= self.max_data_lines)):
                self._open(when)
            sample_clock = captured_monotonic if captured_monotonic is not None else time.monotonic()
            values = {
                "timestamp": when.isoformat(timespec="microseconds"),
                "unix_timestamp": f"{timestamp:.6f}",
                "elapsed_s": f"{sample_clock - self._start:.6f}",
                "sequence": self.saved_count + 1,
                "adc_source": type(self.adc).__name__,
                "input_mode": "single-ended" if getattr(self.adc, "single_ended", True) else "differential",
                "gain": getattr(self.adc, "gain", ""),
                "vref_V": getattr(self.adc, "vref", ""),
                "averaging": self.averaging,
            }
            values.update({key: value for key, value in metadata.items() if key != "channels"})
            for channel, captured in metadata.get("channels", {}).items():
                values.update((f"{channel_name(channel)}_{key}", value)
                              for key, value in captured.items())
            values.update((f"{channel_name(ch)}_mV", format(readings[ch] * 1000.0, ".12g"))
                          for ch in self.channels if f"{channel_name(ch)}_mV" in self.included_columns)
            self._writer.writerow([values.get(column, "") for column in self.included_columns])
            self._sync()
            self.saved_count += 1
            self.file_saved_count += 1
            self.current_file_bytes = self._file.tell()
            self.last_saved_timestamp = timestamp
        except Exception as exc:
            self.error = exc
            raise

    def close(self):
        if self._file is not None:
            handle = self._file
            self._file = None
            self._writer = None
            handle.close()
