"""Durable, daily CSV recording without a growing in-memory backlog."""
import csv
from datetime import datetime
import os
from pathlib import Path
import time
from uuid import uuid4


def channel_name(channel):
    if isinstance(channel, (tuple, list)) and len(channel) == 2:
        return f"AD{channel[0]}-AD{channel[1]}"
    return f"CH{channel}"


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

    def __init__(self, directory, channels, adc, averaging=1):
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
        self.adc = adc
        self.averaging = averaging
        self.session = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex
        self.path = None
        self._file = None
        self._writer = None
        self._day = None
        self._part = 0
        self._start = time.monotonic()
        self.saved_count = 0
        self.last_saved_timestamp = None
        self.error = None

    def _sync(self):
        self._file.flush()
        os.fsync(self._file.fileno())

    def _open(self, day):
        self.close()
        self._part += 1
        self.path = self.directory / f"voltmeter_{day}_{self.session}_{self._part}.csv"
        self._file = self.path.open("x", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp", "unix_timestamp", "elapsed_s", "sequence", "adc_source",
            "input_mode", "gain", "vref_V", "averaging",
        ] + [f"{channel_name(ch)}_mV" for ch in self.channels])
        self._sync()
        # fsync(file) alone does not persist its new directory entry on Linux.
        sync_directory(self.directory)
        self._day = day

    def write(self, timestamp, readings):
        if self.error is not None:
            raise RuntimeError(f"Recording previously failed: {self.error}")
        try:
            when = datetime.fromtimestamp(timestamp).astimezone()
            day = when.strftime("%Y%m%d")
            if self._file is None or self._day != day:
                self._open(day)
            self._writer.writerow([
                when.isoformat(timespec="microseconds"), f"{timestamp:.6f}",
                f"{time.monotonic() - self._start:.6f}", self.saved_count + 1,
                type(self.adc).__name__,
                "single-ended" if getattr(self.adc, "single_ended", True) else "differential",
                getattr(self.adc, "gain", ""), getattr(self.adc, "vref", ""), self.averaging,
            ] + [format(readings[ch] * 1000.0, ".12g") for ch in self.channels])
            self._sync()
            self.saved_count += 1
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
