# PyQt Voltmeter (Raspberry Pi)

This project provides a simple PyQt-based voltmeter UI that reads from an ADC device.

Features:

- Mock ADC for development without hardware
- Background acquisition manager
- PyQt6 UI with live plotting (pyqtgraph)
- Terminal serial monitor (no GUI)

Quick start (on Raspberry Pi or dev machine):

1. Create a Python environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
```

2. Run the app (uses mock ADC by default):

```bash
python main.py
```

3. Run without GUI (serial monitor):

```bash
python serial_monitor.py --rate 10 --channels 0
```

Mock mode for testing on non-RPi:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

Next steps:

- Implement concrete ADC drivers in `hardware/adc.py` for your board (ADS1115, ADS1256, MCP3008, etc.)
- Add calibration and unit tests
- Optionally switch to `PyQtGraph` advanced plotting features for timestamps and multi-channel overlays
