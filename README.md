# PyQt Voltmeter for Raspberry Pi

Simple Raspberry Pi voltmeter application with a PyQt6 GUI, live plotting, a terminal-only monitor, and a mock ADC fallback for development without hardware.

## Current Hardware Target

The implemented real ADC driver targets the Waveshare ADS1256-based High-Precision AD/DA board.

The default application mode is tuned for low-level millivolt differential measurement from a concrete resistance measurement instrument:

- SPI library: `spidev`
- GPIO library: `RPi.GPIO`
- SPI bus/device: `0, 0`
- SPI speed: `20000` Hz
- SPI mode: `0b01`
- DRDY pin: BCM `17`, pull-up enabled
- RESET pin: BCM `18`
- Manual CS pin: BCM `22`
- Expected ADS1256 chip ID: `3`
- Input mode: differential `AD0-AD1`
- PGA gain: `64`
- ADC data rate: `30` SPS by default
- Vref: `2.5` V

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
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
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

Run terminal monitor against ADS1256 and fail clearly if hardware cannot initialize:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
```

Run terminal monitor against ADS1256 or fallback mock in `auto` mode:

```bash
python serial_monitor.py --rate 30 --channels 0-1 --count 10
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
- On Raspberry Pi OS, use the provided `setup.sh`; it installs `spidev` plus
  `RPi.GPIO` on Pi 4 and older or the compatible `rpi-lgpio` backend on Pi 5.
- Double-click `run_voltmeter.sh` in the project folder to start `main.py` with
  `.venv/bin/python`; manual virtualenv activation is not needed.
- The ADS1256 path requires real Raspberry Pi GPIO/SPI access.
- Voltage conversion in differential mode uses `Voltage = Raw_Data * 2 * VREF / (8388607 * GAIN)`.
- Keep hardware-specific changes inside `hardware/`.

## Wiring For mV Differential Measurement

Connect the concrete resistance measurement instrument voltage output to the ADS1256 differential input:

| Signal | Waveshare terminal |
| --- | --- |
| Positive voltage output | `AD0` / `AIN0` |
| Negative voltage output | `AD1` / `AIN1` |
| Reference/common shield, if required by the instrument | instrument manual dependent |

Raspberry Pi to Waveshare board signals are provided through the 40-pin header. The relevant ADS1256 pins are:

| ADS1256 signal | Raspberry Pi BCM |
| --- | ---: |
| `DRDY` | 17 |
| `RESET` | 18 |
| `CS0` | 22 |
| `DIN` / MOSI | 10 |
| `DOUT` / MISO | 9 |
| `SCK` | 11 |

Do not connect the measured differential pair directly to Raspberry Pi GPIO pins. Connect it only to the ADS1256 analog inputs. Keep the signal leads short and twisted where possible to reduce noise.
