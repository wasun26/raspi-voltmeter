# Setup

Setup instructions for Raspberry Pi OS and development machines.

## Raspberry Pi OS

### Prerequisites

- Raspberry Pi with Raspberry Pi OS
- SPI enabled
- ADS1256 board wired to the configured GPIO pins
- Internet connection for package installation

Default ADS1256 wiring/configuration:

| Signal | BCM pin |
| --- | ---: |
| DRDY | 17 |
| RESET | 18 |
| CS | 22 |
| SPI bus/device | 0 / 0 |

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
python serial_monitor.py --rate 10 --channels 0 --count 10
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
- `RPi.GPIO`

The provided `setup.sh` installs Raspberry Pi system packages including `python3-spidev`. If your Raspberry Pi OS image does not already provide `RPi.GPIO`, install it with:

```bash
sudo apt-get install python3-rpi.gpio
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
    "gain": 1,
    "data_rate": 1000,
    "single_ended": True,
    "validate_chip_id": True,
    "expected_chip_id": 3,
}
```

Use `"type": "mock"` to force mock mode. Use `"type": "ads1256"` to require real hardware and fail if the ADS1256 cannot initialize.

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

### GUI display issues over SSH

Use a directly connected display or X11 forwarding. For hardware validation without a display, use:

```bash
python serial_monitor.py --rate 10 --channels 0 --count 10
```

### Non-Raspberry Pi testing

Use mock mode:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```
