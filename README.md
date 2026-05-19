# PyQt Voltmeter for Raspberry Pi

Simple Raspberry Pi voltmeter application with a PyQt6 GUI, live plotting, a terminal-only monitor, and a mock ADC fallback for development without hardware.

## Current Hardware Target

The implemented real ADC driver targets the Waveshare ADS1256-based High-Precision AD/DA board.

Default ADS1256 settings are kept close to the Waveshare Python sample:

- SPI library: `spidev`
- GPIO library: `RPi.GPIO`
- SPI bus/device: `0, 0`
- SPI speed: `20000` Hz
- SPI mode: `0b01`
- DRDY pin: BCM `17`, pull-up enabled
- RESET pin: BCM `18`
- Manual CS pin: BCM `22`
- Expected ADS1256 chip ID: `3`
- ADC data rate: `1000` SPS by default
- Vref: `2.5` V
- Gain: `1`

Configuration lives in `config.py`.

## Features

- ADS1256 driver using `spidev` and `RPi.GPIO`
- Mock ADC for Windows, macOS, Linux, and non-Raspberry Pi development
- Safe `auto` mode that falls back to mock ADC when hardware is unavailable
- Background acquisition manager
- PyQt6 UI with live plotting via `pyqtgraph`
- Terminal-only monitor for SSH and hardware validation

## Quick Start

### Raspberry Pi OS

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
sudo reboot
```

After reboot:

```bash
source .venv/bin/activate
python serial_monitor.py --rate 10 --channels 0 --count 10
python main.py
```

### Development Machine

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python serial_monitor.py --mock --rate 5 --count 5
python main.py
```

On non-Raspberry Pi machines, `main.py` and `serial_monitor.py` use `MockAdc` when `config.py` has `adc.type = "auto"`.

## Useful Commands

Run terminal monitor with mock ADC:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

Run terminal monitor against ADS1256 or fallback mock in `auto` mode:

```bash
python serial_monitor.py --rate 10 --channels 0 --count 10
```

Run the GUI:

```bash
python main.py
```

## Project Layout

```text
raspi-voltmeter/
|-- main.py                 # PyQt6 GUI entry point
|-- serial_monitor.py       # Terminal monitor entry point
|-- config.py               # Runtime configuration
|-- requirements.txt        # Cross-platform Python dependencies
|-- setup.sh                # Raspberry Pi OS setup helper
|-- setup.ps1               # Windows development setup helper
|-- hardware/
|   `-- adc.py              # MockAdc and ADS1256 driver
|-- core/
|   `-- acquisition.py      # Background acquisition manager
|-- gui/
|   |-- main_window.py      # Main PyQt6 window
|   `-- chart.py            # Plotting helpers
`-- Wasveshare - Sample/    # Vendor samples used as ADS1256 reference
```

## Notes

- `requirements.txt` intentionally contains portable GUI/data packages only.
- On Raspberry Pi OS, install `spidev` and `RPi.GPIO` through system packages or the provided `setup.sh`.
- The ADS1256 path requires real Raspberry Pi GPIO/SPI access.
- Keep hardware-specific changes inside `hardware/`.
