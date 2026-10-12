# Setup

Setup instructions for Raspberry Pi OS and development machines.

## macOS

Python 3 is required. Then run:

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
./run_voltmeter.sh
```

The macOS path creates `.venv`, installs `requirements.txt`, and skips the
Raspberry Pi-only GPIO/SPI setup. With `adc.type = "auto"`, it uses `MockAdc`.

## Raspberry Pi OS

### Prepare one-click updates

Install the project using `git clone` and keep its `main` branch tracking
`origin/main`. After the initial `bash setup.sh`, operators can click
**Check for updates** in the app whenever the maintainer pushes a new commit.
The Pi needs internet access for the check and for any new Python packages.
The updater does not run `sudo` or upgrade Raspberry Pi OS packages; hardware
or system package changes still require an administrator.

Keep site-specific code edits out of tracked files. Changes to `config.py` or
other tracked files block the automated update to protect those edits. Saved
CSV files in `logs/` and `recording_settings.json` remain on the Pi. Updating
stops acquisition and creates a measurement gap before the app restarts.

### Prerequisites

- Raspberry Pi with Raspberry Pi OS
- SPI enabled
- ADS1256 board wired to the configured GPIO pins
- Internet connection for package installation

Default ADS1256 wiring/configuration for the Raspberry Pi side:

| Signal | BCM pin |
| --- | ---: |
| DRDY | 17 |
| RESET | 18 |
| CS | 22 |
| SPI bus/device | 0 / 0 |

Default analog input wiring for the concrete resistance measurement instrument:

| Instrument output | Waveshare ADS1256 input |
| --- | --- |
| Positive mV signal | `AD0` / `AIN0` |
| Negative mV signal | `AD1` / `AIN1` |

The application reads this as differential `AD0-AD1`, with `GAIN=64` and `30 SPS`.

### Quick Setup

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
sudo reboot
```

The setup script installs Python/Qt dependencies, enables SPI/I2C where possible, creates `.venv`, and installs `requirements.txt`.

After reboot:

```bash
cd /path/to/raspi-voltmeter
source .venv/bin/activate
```

Verify SPI device nodes:

```bash
ls /dev/spi*
```

Run the terminal monitor:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
```

Run the GUI:

```bash
python main.py
```

## Development Machine

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
.venv\Scripts\activate
python serial_monitor.py --mock --rate 5 --count 5
python main.py
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python serial_monitor.py --mock --rate 5 --count 5
python main.py
```

## Dependencies

Portable dependencies in `requirements.txt`:

- `PyQt6`
- `pyqtgraph`
- `numpy`

Raspberry Pi OS hardware dependencies:

- `spidev`
- `RPi.GPIO` on Raspberry Pi 4 and older
- `rpi-lgpio` on Raspberry Pi 5 (it provides an `RPi.GPIO`-compatible API)

The provided `setup.sh` detects both 32-bit `arm*` and 64-bit `aarch64`, selects
the GPIO package for the detected Raspberry Pi model, and creates the virtual
environment with access to system packages. To install the GPIO package manually:

```bash
# Raspberry Pi 4 and older
sudo apt-get install python3-rpi.gpio

# Raspberry Pi 5
sudo apt-get install python3-rpi-lgpio
```

To start the GUI with the project's `.venv` automatically, double-click
`run_voltmeter.sh` in the project folder or run:

```bash
./run_voltmeter.sh
```

## Configuration

Runtime defaults are in `config.py`.

Important ADS1256 fields:

```python
"adc": {
    "type": "auto",
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
}
```

Use `"type": "mock"` to force mock mode. Use `"type": "ads1256"` to require real hardware and fail if the ADS1256 cannot initialize.

You can also force real hardware from the terminal without editing `config.py`:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
```

The default channel list is:

```python
"channels": [(0, 1)]
```

This means differential `AD0-AD1`.

## Troubleshooting

### SPI device missing

```bash
sudo raspi-config
```

Enable SPI under Interface Options, reboot, then check:

```bash
ls /dev/spi*
```

### Permission denied for GPIO or SPI

Run the setup script, then reboot so group changes apply:

```bash
bash setup.sh
sudo reboot
```

### ADS1256 chip ID mismatch

Check wiring, power, SPI enablement, and the configured pins in `config.py`. The default expected chip ID is `3`, matching the Waveshare sample.

### Reading clips or stays near range limit

With `VREF=2.5V` and `GAIN=64`, the differential full-scale range is approximately:

```text
+/-78.125 mV
```

If the measured signal can exceed this range, reduce gain to `32`, `16`, or `8` in `config.py`.

### GUI display issues over SSH

Use a directly connected display or X11 forwarding. For hardware validation without a display, use:

```bash
python serial_monitor.py --rate 30 --channels 0-1 --count 10
```

### Non-Raspberry Pi testing

Use mock mode:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

## Unattended recording on Raspberry Pi OS

For an attached-display GUI deployment, use **Data collection mode** (`Ctrl+M`)
to stop graph work and refresh status every 3 seconds while CSV recording
continues. Set `collection_mode_on_start` to `True` in `config.py` to enter it at
startup. With no display, use the terminal service below to avoid GUI overhead.

Verify CSV output before installing the service:

```bash
python serial_monitor.py --adc ads1256 --channels 0-1 --rate 30 --count 10
```

CSV files are in `logs/` by default. Confirm that `adc_source` is `ADS1256` and
that the `AD0-AD1_mV` column has ten data rows.

Recording defaults in `config.py` limit each CSV to 100,000 data rows and reserve
100 MiB of free drive space. Full files roll over without stopping; low space
pauses new ADC readings and retries without deleting existing data. GUI Recording settings can
remember overrides in `recording_settings.json`, which also affect terminal
startup. CLI options such as `--max-data-lines` and `--min-free-mb` override them
for a run. Check these settings before enabling the unattended service.

Edit `voltmeter.service.example`: replace `User=pi`, `WorkingDirectory`, the Python
path, and `--log-dir` with actual absolute paths. The user must have GPIO/SPI access
and write permission to the recording directory. For an external drive, configure
its mount and enable the matching `RequiresMountsFor` line so the service waits
for that drive instead of writing into an unmounted directory.

```bash
sudo cp voltmeter.service.example /etc/systemd/system/voltmeter.service
sudo systemctl daemon-reload
sudo systemctl enable --now voltmeter.service
systemctl status voltmeter.service
journalctl -u voltmeter.service -f
```

Do not run the GUI and service against the ADC simultaneously. Stop the service
with `sudo systemctl stop voltmeter.service` before manual hardware tests.
The service starts after reboot and retries failed runs every ten seconds. During
a storage outage, the running process pauses ADC reads, retries its pending sample
every five seconds by default, and resumes automatically when storage returns.
Check storage capacity for the whole deployment; an outage leaves a measurement
gap, and stopping during an outage discards the unsaved pending sample.

Before deployment, test stopping/restarting and abruptly removing power on the
actual storage setup. Previously synced rows should remain readable; an unfinished
last row may be incomplete. The local development tests do not validate Linux
directory syncing, SD-card behavior, or real power-loss recovery.
