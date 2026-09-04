# Agents

Guidelines for automated agents working in this repository.

## Project Context

- Thai project title: **การพัฒนาต้นแบบและการวัดสัญญาณของวัสดุผสมเพียโซอิเล็กทริกที่มีซีเมนต์เป็นฐานสำหรับการใช้เซ็นเซอร์ในการตรวจสอบสภาพโครงสร้าง**
- English working title: **Prototype Development and Signal Measurement of Cement-Based Piezoelectric Composites for Structural Health Monitoring Sensor Applications**.
- The specimens are cement-based piezoelectric composites embedded in or loaded with concrete. Applied load produces an electrical signal for structural-health-monitoring research.
- Treat the direct measurement as voltage until documented calibration converts it to charge, force, stress, strain, or another engineering quantity. Never label raw voltage as strain.

## Scope

- Prioritize Raspberry Pi 5 and Raspberry Pi OS while preserving Raspberry Pi 4 support.
- Keep macOS and non-Raspberry Pi development functional through `MockAdc`.
- Keep ADS1256 behavior aligned with the Waveshare Python sample when practical.
- `adc.type = "auto"` must fall back to `MockAdc` when hardware is unavailable.
- Keep the PyQt6 UI simple and use specimen names `EX1`, `EX2`, and `EX3` in user-facing features.

## Measurement Model

- Plan three differential inputs: `EX1 = AIN0-AIN1`, `EX2 = AIN2-AIN3`, and `EX3 = AIN4-AIN5`. Reserve `AIN6-AIN7` as a spare/reference.
- ADS1256 is multiplexed. EX1-EX3 are sampled sequentially, not simultaneously; UI, logs, and documentation must say so accurately.
- Timestamp every actual channel conversion. Distinguish ADC data rate, aggregate scan rate, and effective per-channel rate.
- Piezoelectric signals can be bipolar, transient, and high impedance. Do not assume static load produces sustained DC voltage.
- Before changing gain or rate, consider peak voltage, event duration, source impedance, switching-settling time, and required bandwidth.
- Retain raw voltage alongside derived values. Calibration metadata includes specimen ID, coefficients, units, date, method, reference load, gain, data rate, and conditioning circuit.

## Hardware and Safety

- Hardware access stays in `hardware/`; acquisition and timing stay in `core/`; UI stays in `gui/`; configuration stays in `config.py`.
- The real ADC is `ADS1256` in `hardware/adc.py` and uses `spidev` plus an `RPi.GPIO`-compatible API.
- Raspberry Pi 5 uses `rpi-lgpio`; Raspberry Pi 4 and older use `RPi.GPIO`.
- Preserve Waveshare-style settings: `SpiDev(0, 0)`, `writebytes/readbytes`, manual CS BCM 22, DRDY BCM 17 with pull-up, RESET BCM 18, SPI 20000 Hz, mode `0b01`.
- Do not set `spi.no_cs`; Raspberry Pi 5 RP1 may reject it and CS is controlled manually.
- Current low-level defaults are gain 64, 30 SPS, differential mode, and VREF 2.5 V. Conversion is `Raw_Data * 2 * VREF / (8388607 * GAIN)`.
- At gain 64 and VREF 2.5 V, nominal differential full scale is about +/-78.125 mV. Validate actual analog limits first.
- Never connect an uncharacterized piezoelectric specimen directly to ADS1256. Establish peak voltage and impedance, then provide protection, bias/return path, filtering, buffering, or a charge amplifier as needed.
- Review protection and conditioning before impact, fracture, or other fast-transient tests.

## Coding and Data

- Use plain Python 3 and avoid heavy frameworks.
- Keep raw acquisition separate from calibration and display transforms.
- Research logs must use explicit units and enough metadata to reproduce the measurement.
- Do not add large binary measurement datasets to the repository.

## Testing

Mock three-channel scan:

```bash
python serial_monitor.py --mock --rate 5 --channels 0-1,2-3,4-5 --count 5
```

Validate one real input before three specimens:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
```

Then validate the sequential three-input scan:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1,2-3,4-5 --count 30
```

- Test open input, shorted differential input, known voltage, idle specimen, and controlled load cases.
- Mock tests do not demonstrate hardware accuracy.

## Documentation

- When changing defaults, mappings, units, calibration, GPIO, or SPI setup, update `README.md`, `SETUP.md`, and `PLANNING.md` together.
- Clearly mark capabilities as planned, implemented, or hardware-validated.
