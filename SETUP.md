# Setup

Setup instructions for Raspberry Pi OS and development machines.

## Raspberry Pi OS

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
