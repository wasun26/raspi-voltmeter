#!/bin/bash
# Complete setup script for Raspberry Pi OS
# Run: bash setup.sh

set -e

echo "=========================================="
echo "PyQt Voltmeter - Raspberry Pi Setup"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if ! uname -a | grep -q "arm"; then
    echo -e "${RED}Warning: This doesn't appear to be ARM architecture${NC}"
    echo "Proceeding anyway..."
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
sudo usermod -a -G i2c,gpio,dialout $(whoami)

echo -e "\n${YELLOW}[4/5] Creating Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
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
echo "   python tests/run_gui_demo.py"
echo ""
echo "3. Check I2C devices:"
echo "   i2cdetect -y 1"
echo ""
echo "4. Check SPI devices:"
echo "   sudo ls /dev/spi*"
echo ""
echo "5. To implement real ADC driver, edit: hardware/adc.py"
echo ""
