import json
import os
from pathlib import Path
import tempfile


RECORDING_SETTINGS_PATH = Path(__file__).resolve().parent / "recording_settings.json"

DEFAULT = {
    "adc": {
        "type": "auto",
        "i2c_address": 0x48,
        "spi_bus": 0,
        "spi_device": 0,
        "drdy_pin": 17,
        "reset_pin": 18,
        "cs_pin": 22,
        "spi_hz": 20000,
        "vref": 2.5,
        "gain": 64,
        "data_rate": 30,
        "single_ended": False,
        "validate_chip_id": True,
        "expected_chip_id": 3,
        "mock_amplitude": 0.012,
        "mock_offset": 0.0,
    },
    "sample_rate": 30,
    "channels": [(0, 1)],
    "averaging": 1,
    "plot_window_sec": 60,
    "plot_max_points": 2000,
    "log_enabled": True,
    # CSV is synced after every sample. Use an absolute path for an external drive.
    "log_dir": "logs",
    "recording": {
        "max_data_lines": 100000,  # Excludes the header; 0 means no line limit.
        "file_prefix": "voltmeter",
        "rotate_daily": True,
        "min_free_mb": 100,  # Stop when drive free space drops below this.
    },
}


def load_recording_settings(path=RECORDING_SETTINGS_PATH):
    settings = dict(DEFAULT["recording"], directory=DEFAULT["log_dir"])
    if Path(path).exists():
        with Path(path).open(encoding="utf-8") as handle:
            saved = json.load(handle)
        if not isinstance(saved, dict):
            raise ValueError("Recording settings must be a JSON object")
        settings.update({key: saved[key] for key in settings if key in saved})
    return settings


def save_recording_settings(settings, path=RECORDING_SETTINGS_PATH):
    """Replace saved preferences atomically without affecting measurement CSVs."""
    destination = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".recording_settings_", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(settings, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        if os.name == "posix":
            fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
