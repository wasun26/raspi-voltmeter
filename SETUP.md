# Complete setup instructions for Raspberry Pi OS

## Prerequisites

- Raspberry Pi 4B (or higher) with Raspberry Pi OS (Debian-based)
- Internet connection
- SSH access or direct terminal

## Quick Setup (One Command)

On Raspberry Pi OS terminal:

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
```

This will:

1. ✓ Update package manager
2. ✓ Install all system dependencies (PyQt6, Qt libraries, I2C/SPI tools)
3. ✓ Enable I2C and SPI interfaces
4. ✓ Create Python virtual environment
5. ✓ Install Python packages (PyQt6, pyqtgraph, numpy, smbus2, spidev)
6. ✓ Add user to I2C/GPIO groups (no password needed after reboot)

## After Setup

### 1. Reboot (required for I2C/SPI and group changes)

```bash
sudo reboot
```

### 2. Verify hardware interfaces

```bash
# Check I2C devices
i2cdetect -y 1

# Check SPI devices
sudo ls /dev/spi*
```

### 3. Run real application (GUI)

```bash
source .venv/bin/activate
python main.py
```

### 4. Run terminal-only monitor (no GUI)

```bash
source .venv/bin/activate
python serial_monitor.py --rate 10 --channels 0
```

## Next: Implement ADC Driver

Edit `hardware/adc.py` to implement your specific ADC board:

### Example: ADS1115 (I2C)

```python
import smbus2
import time

class ADS1115(AdcDevice):
    def __init__(self, i2c_addr=0x48, channel=0):
        self.bus = smbus2.SMBus(1)
        self.addr = i2c_addr
        self.channel = channel

    def read_voltage(self, channel=0):
        # Read from ADS1115 register
        # Convert to voltage (typically 0-6.144V range)
        pass
```

### Example: ADS1256 (SPI)

```python
import spidev

class ADS1256(AdcDevice):
    def __init__(self, bus=0, device=0):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 1000000

    def read_voltage(self, channel=0):
        # SPI communication to ADS1256
        # Convert to voltage
        pass
```

## Troubleshooting

### I2C not detected

```bash
# Check if i2c kernel module is loaded
lsmod | grep i2c

# Check devices
ls /dev/i2c*
```

### Permission denied on /dev/i2c-\*

```bash
# Add user to i2c group
sudo usermod -a -G i2c $USER
sudo reboot
```

### PyQt6 display issues

- Use X11 forwarding if SSH: `ssh -X user@raspberrypi`
- Or connect HDMI display directly
- Or use terminal-only monitor: `python serial_monitor.py`

### Module not found errors

```bash
# Ensure venv is activated
source .venv/bin/activate
which python  # Should show .venv/bin/python
```

## File Structure

```
raspi-voltmeter/
├── main.py                 # Main application
├── serial_monitor.py       # Terminal serial monitor (no GUI)
├── config.py              # Configuration
├── requirements.txt       # Python dependencies
├── setup.sh              # Setup script (THIS FILE)
├── hardware/
│   └── adc.py           # ADC drivers (modify for your board)
├── core/
│   └── acquisition.py   # Data acquisition manager
├── gui/
│   ├── main_window.py   # PyQt UI
│   └── chart.py         # Plotting helpers

```

## Support

For issues:

1. Check troubleshooting section above
2. Verify I2C/SPI is enabled: `raspi-config` → Interface Options
3. Run `python serial_monitor.py` to verify readings
4. Check hardware connections and I2C address
