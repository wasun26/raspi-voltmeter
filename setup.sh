#!/bin/bash
# Complete setup script for Raspberry Pi OS
# Run: bash setup.sh

set -e

# Always create files beside this script, even when it is launched from another
# working directory (for example: bash /home/pi/raspi-voltmeter/setup.sh).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

trap 'echo -e "\n${RED}Setup stopped at line ${LINENO}. Fix the error above, then run bash setup.sh again.${NC}" >&2' ERR

echo "=========================================="
echo "PyQt Voltmeter - Raspberry Pi Setup"
echo "=========================================="
echo "Project directory: $SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect both 32-bit ARM (armv*) and 64-bit ARM (aarch64). Raspberry Pi 5
# normally reports aarch64, which the old `grep arm` check did not match.
ARCH="$(uname -m)"
case "$ARCH" in
    arm*|aarch64)
        echo -e "${GREEN}✓ ARM architecture detected: ${ARCH}${NC}"
        ;;
    *)
        echo -e "${RED}Warning: This doesn't appear to be ARM architecture: ${ARCH}${NC}"
        echo "Proceeding anyway..."
        ;;
esac

PI_MODEL=""
if [ -r /proc/device-tree/model ]; then
    PI_MODEL="$(tr -d '\000' < /proc/device-tree/model)"
    echo "Detected board: ${PI_MODEL}"
fi

# Pi 5 uses the RP1 GPIO controller. rpi-lgpio provides the RPi.GPIO-compatible
# API used by the Waveshare-style ADS1256 driver. Older models use RPi.GPIO.
GPIO_PACKAGE="python3-rpi.gpio"
if [[ "$PI_MODEL" == *"Raspberry Pi 5"* ]]; then
    GPIO_PACKAGE="python3-rpi-lgpio"
fi

echo -e "\n${YELLOW}[1/5] Updating package manager...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

echo -e "\n${YELLOW}[2/5] Installing system dependencies...${NC}"
sudo apt-get install -y \
    python3-venv \
    python3-dev \
    python3-pyqt6 \
    libqt6gui6 \
    libqt6core6 \
    libgl1 \
    libxkbcommon-x11-0 \
    i2c-tools \
    python3-smbus2 \
    python3-spidev \
    "$GPIO_PACKAGE" \
    build-essential \
    git

echo -e "\n${YELLOW}[3/5] Enabling I2C and SPI interfaces...${NC}"

# Enable I2C
if grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null || \
   grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "✓ I2C already enabled"
else
    echo "Enabling I2C..."
    sudo sed -i 's/#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/firmware/config.txt 2>/dev/null || \
    sudo sed -i 's/#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/config.txt 2>/dev/null || true
    echo "⚠ Please reboot after setup: sudo reboot"
fi

# Enable SPI
if grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null || \
   grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "✓ SPI already enabled"
else
    echo "Enabling SPI..."
    sudo sed -i 's/#dtparam=spi=on/dtparam=spi=on/' /boot/firmware/config.txt 2>/dev/null || \
    sudo sed -i 's/#dtparam=spi=on/dtparam=spi=on/' /boot/config.txt 2>/dev/null || true
    echo "⚠ Please reboot after setup: sudo reboot"
fi

# Add user to i2c and gpio groups
echo "Adding user to i2c and gpio groups..."
SETUP_USER="${SUDO_USER:-$(id -un)}"
sudo usermod -a -G i2c,gpio,dialout "$SETUP_USER"

echo -e "\n${YELLOW}[4/5] Creating Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
    echo "✓ Virtual environment created"
else
    # Make apt-installed spidev and GPIO bindings visible in an existing venv.
    python3 -m venv --upgrade --system-site-packages .venv
    echo "✓ Virtual environment updated"
fi

echo -e "\n${YELLOW}[5/5] Installing Python packages...${NC}"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "\n${GREEN}=========================================="
echo "✓ Setup complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Reboot for I2C/SPI changes to take effect:"
echo "   sudo reboot"
echo ""
echo "2. After reboot, activate venv and run demo:"
echo "   source .venv/bin/activate"
echo "   python serial_monitor.py --mock --rate 5 --count 5"
echo ""
echo "3. Check I2C devices:"
echo "   i2cdetect -y 1"
echo ""
echo "4. Check SPI devices:"
echo "   sudo ls /dev/spi*"
echo ""
echo "5. To validate ADS1256 hardware:"
echo "   python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10"
echo ""
