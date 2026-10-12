import json
import os
from pathlib import Path
import tempfile


RECORDING_SETTINGS_PATH = Path(__file__).resolve().parent / "recording_settings.json"
GAIN_SETTINGS_PATH = Path(__file__).resolve().parent / "gain_settings.json"

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
    "auto_gain": {
        "enabled": False,  # Select Auto in the GUI, or enable for unattended startup.
        "min_gain": 1,
        "max_gain": 64,
        "high_fraction": 0.8,
        "low_fraction": 0.2,
        "quiet_seconds": 10,
        "cooldown_seconds": 3,
    },
    "plot_window_sec": 60,
    "plot_max_points": 2000,
    "collection_mode_on_start": False,
    "collection_ui_refresh_ms": 3000,
    "log_enabled": True,
    # CSV is synced after every sample. Use an absolute path for an external drive.
    "log_dir": "logs",
    "recording": {
        "max_data_lines": 100000,  # Excludes the header; 0 means no line limit.
        "file_prefix": "voltmeter",
        "rotate_daily": True,
        "min_free_mb": 100,  # Stop when drive free space drops below this.
        "included_columns": None,  # All columns by default; timestamp and one mV channel are required.
        "retry_interval_sec": 5,  # Retry one pending sample; no unbounded queue.
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


def load_gain_settings(path=GAIN_SETTINGS_PATH):
    settings = {"auto": DEFAULT["auto_gain"]["enabled"], "gain": DEFAULT["adc"]["gain"]}
    if Path(path).exists():
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if (not isinstance(saved, dict) or not isinstance(saved.get("auto"), bool)
                or not isinstance(saved.get("gain"), int) or isinstance(saved.get("gain"), bool)
                or saved.get("gain") not in (1, 2, 4, 8, 16, 32, 64)):
            raise ValueError("Invalid saved gain settings")
        settings.update(auto=saved["auto"], gain=saved["gain"])
    return settings


def save_gain_settings(gain, path=GAIN_SETTINGS_PATH):
    save_recording_settings({"auto": gain is None, "gain": gain if gain is not None else 1}, path)


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
