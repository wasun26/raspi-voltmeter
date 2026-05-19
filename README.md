# PyQt Voltmeter (Raspberry Pi)

This project provides a simple PyQt-based voltmeter UI that reads from an ADC device.

Features:

- Mock ADC for development without hardware
- Background acquisition manager
- PyQt6 UI with live plotting (pyqtgraph)

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

Next steps:

- Implement concrete ADC drivers in `hardware/adc.py` for your board (ADS1115, ADS1256, MCP3008, etc.)
- Add calibration and unit tests
- Optionally switch to `PyQtGraph` advanced plotting features for timestamps and multi-channel overlays
