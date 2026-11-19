# Planning

Auto gain: implemented for GUI and terminal, with shared sequential-scan gain,
x1 startup, 80% reduction threshold, 20%/10-second quiet increase criterion and
3-second increase cooldown. GUI gain-mode choices persist across restarts/updates
and override config. Manual x64 remains default. Acquisition owns gain
changes; ADS1256 waits for automatic calibration and verifies the PGA register.
CSV retains capture-time gain, per-conversion raw counts/timestamps, clipping and
gain-change metadata even across storage retries. Auto requires these fields.
Mock and driver-call tests cover bipolar clipping, averaging, channel peaks,
hysteresis and metadata preservation. Real hardware settling, timing gaps,
source-loading effects at different gains and transient accuracy remain planned
validation. Input protection/bias and common-mode review remain prerequisites.

Software versioning: implemented with `VERSION` and matching Git release tags,
starting at `v0.1.0`. The update dialog displays release numbers and commit IDs;
updates continue to follow new commits on `origin/main`. Raspberry Pi update
behavior remains to be hardware-validated.

## Project

**การพัฒนาต้นแบบและการวัดสัญญาณของวัสดุผสมเพียโซอิเล็กทริกที่มีซีเมนต์เป็นฐานสำหรับการใช้เซ็นเซอร์ในการตรวจสอบสภาพโครงสร้าง**

Working English title: **Prototype Development and Signal Measurement of Cement-Based Piezoelectric Composites for Structural Health Monitoring Sensor Applications**.

## Objective

Develop a Raspberry Pi-based prototype that safely acquires, displays, and records electrical signals from three cement-based piezoelectric composite specimens under controlled concrete loading. Preserve raw voltage and support traceable calibration to engineering quantities when experimental calibration becomes available.

## Architecture and Channel Plan

```text
Applied load / structural event
  -> cement-based piezoelectric specimens EX1-EX3
  -> protection and signal conditioning
  -> ADS1256 differential multiplexer
  -> Raspberry Pi 5
  -> timestamp, visualization, and research log
  -> optional calibrated engineering value
```

| Specimen | ADS1256 pair | Acquisition |
| --- | --- | --- |
| EX1 | AIN0-AIN1 | Differential |
| EX2 | AIN2-AIN3 | Differential |
| EX3 | AIN4-AIN5 | Differential |
| Spare/reference | AIN6-AIN7 | Differential |

ADS1256 has one converter behind a multiplexer, so EX1-EX3 are scanned sequentially. At 30 conversions per second, the ideal upper bound is about 10 conversions per second per specimen before switching and settling overhead. This is not simultaneous sampling.

## Current Baseline

- One-click Git update check and fast-forward installation are implemented in
  the GUI. Local Git and mock tests pass; Raspberry Pi hardware validation is
  still pending. The update stops acquisition and leaves a measurement gap.
- ADS1256 driver, Waveshare-style SPI, manual BCM 22 CS, BCM 17 DRDY, and BCM 18 RESET are implemented.
- Raspberry Pi 5 uses `rpi-lgpio`; Pi 4 retains `RPi.GPIO`; macOS uses `MockAdc` in auto mode.
- Current default is one differential pair AIN0-AIN1, gain 64, 30 SPS, and VREF 2.5 V.
- `serial_monitor.py` already parses multiple differential pairs.
- GUI and default configuration still target one specimen.
- Three-specimen behavior and analog conditioning are planned, not yet hardware-validated.

## Questions to Resolve

1. Expected typical and worst-case bipolar voltage for each specimen.
2. Test type: quasi-static, cyclic, impact, cracking, or a combination.
3. Required event duration and frequency bandwidth.
4. Specimen source impedance and charge sensitivity.
5. Need for a voltage buffer or charge amplifier.
6. Required protection, bias return, shielding, cabling, and grounding.
7. Desired calibrated output: voltage, charge, force, stress, strain, or health indicator.
8. Whether true simultaneous EX1-EX3 sampling is mandatory; if so, ADS1256 must be replaced or supplemented.

## Roadmap

### Phase 1 — Characterize and protect the input

- Record specimen construction, dimensions, electrodes, polarization, cable, and connector.
- Measure impedance and signal amplitude under controlled load with laboratory equipment.
- Define safe ADC limits and design protection/signal conditioning.
- Decide between direct voltage acquisition, buffering, and charge amplification.

Exit: reviewed schematic, expected voltage range, selected gain/rate, and safe connection procedure.

### Phase 2 — Acquire EX1-EX3

- Configure named channels EX1-EX3 using pairs 0-1, 2-3, and 4-5.
- Implement an explicit scan cycle and per-conversion timestamps.
- Validate multiplexer settling and discard/delay the first post-switch conversion if required.
- Report ADC rate, aggregate rate, and measured effective per-channel rate.
- Simulate distinct three-channel signals in mock mode.

Exit: stable three-channel terminal acquisition with verified timing and labels.

### Phase 3 — Research logging

- Define versioned CSV fields: timestamp, elapsed time, specimen, pair, raw count, raw voltage, gain, rate, and flags.
- Record test ID, batch, load protocol, operator, calibration ID, and notes.
- Use safe filenames and flushing; record dropped samples, clipping, errors, and mock fallback.

Exit: a saved experiment is interpretable without undocumented UI state.

### Phase 4 — Calibration and processing

- Add per-specimen baseline capture while retaining raw voltage.
- Add versioned calibration profiles with coefficients, units, range, and provenance.
- Add only filters justified by measured bandwidth.
- Detect clipping, disconnection, abnormal noise, and out-of-calibration values.
- Compare derived output against a traceable reference load instrument.

Exit: calibrated output has documented error/uncertainty and is reproducible from raw logs.

### Phase 5 — EX1-EX3 GUI

- Show three labeled traces, using raw voltage by default.
- Show backend, saturation, effective rate, logging state, and calibration state.
- Add start/stop experiment and deliberate zero/baseline controls.
- Permit raw and calibrated views without discarding raw data.

Exit: an operator can run a three-specimen test without confusing voltage with strain/force.

### Phase 6 — Validate the system

- Test shorted-input noise and each pair with a known safe voltage.
- Quantify settling and crosstalk during scanning.
- Compare against a reference oscilloscope or DAQ.
- Test repeatability, drift, clipping, recovery, cyclic load, and long logging.
- Document Raspberry Pi 5 wiring, operation, shutdown, recovery, and export.

Exit: repeatable end-to-end results and documented limitations for the project report.

## Immediate Next Actions

1. Characterize one EX specimen before direct ADS1256 connection.
2. Confirm slow-load versus fast-transient requirements.
3. Select and review the protection/conditioning circuit.
4. Validate AIN0-AIN1 using a known safe source on Raspberry Pi 5.
5. Implement named EX1-EX3 configuration and conversion timestamps.
6. Measure real three-channel scan rate and settling.

## Main Risks

- Unexpected piezoelectric transients may damage or clip the ADC.
- High source impedance may cause signal loading and slow multiplexer settling.
- A 30 SPS sequential scan may miss impact or fracture events.
- One timestamp per whole scan would hide EX1-EX3 timing offsets.
- Raw voltage could be scientifically mislabeled as force, stress, or strain.
- Long embedded-sensor cables may introduce noise and grounding problems.

## Out of Scope Until Characterized

Durable CSV recording now runs in the acquisition path and terminal monitor:
flush/fsync per reading, daily/session file separation, explicit ADC source and
mV units, stop on recording failure, and graceful shutdown before file closure.
`voltmeter.service.example` provides opt-in unattended startup on Raspberry Pi OS.
Mock tests cover rotation, session preservation, sync failures, and shutdown.
Real hardware, month-long operation, and abrupt power-loss testing remain site
validation tasks.

- Validate with real ADS1256 hardware.
- Add calibration support.
- Add lightweight tests for mock ADC and config-driven ADC creation.
- Update setup scripts if they still reference removed test/demo paths.
- Claiming true simultaneous sampling from one ADS1256.
- Converting voltage to engineering quantities without calibration data.
- Direct impact/fracture connection without protection review.
- Treating mock output as evidence of hardware accuracy.
