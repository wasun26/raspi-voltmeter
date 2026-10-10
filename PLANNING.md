# Planning

## Current Goal

Keep the Raspberry Pi ADS1256 voltmeter stable for low-level millivolt differential measurement from a concrete resistance measurement instrument while matching the Waveshare sample driver behavior and preserving mock-mode development on non-Raspberry Pi machines.

## Current Status

- ADS1256 driver exists in `hardware/adc.py`.
- Driver uses `spidev` and `RPi.GPIO`, matching the Waveshare Python sample dependency model.
- SPI API now follows the sample style: `writebytes(...)` and `readbytes(...)`.
- Manual CS is supported on BCM `22`.
- DRDY uses BCM `17` with pull-up enabled.
- RESET uses BCM `18`.
- SPI speed defaults to `20000` Hz and mode `0b01`.
- Chip ID validation defaults to expected ID `3`.
- Default measurement is differential `AD0-AD1`.
- Default gain is `64`.
- Default data rate is `30` SPS.
- Differential voltage conversion uses `Raw_Data * 2 * VREF / (8388607 * GAIN)`.
- `serial_monitor.py` supports `auto`, `ads1256`, and `mock` flows.
- `auto` mode falls back to `MockAdc` when real hardware is unavailable.

## Completed

1. Aligned ADS1256 driver with Waveshare sample defaults.
2. Added config fields for CS pin, SPI speed, and chip ID validation.
3. Passed ADS1256 config through both GUI and terminal entry points.
4. Kept mock mode working for development machines.
5. Updated defaults for mV differential measurement.
6. Updated Markdown documentation to reflect the implemented driver and wiring.

## Next Validation

Run on Raspberry Pi OS with real ADS1256 hardware:

```bash
source .venv/bin/activate
python serial_monitor.py --rate 30 --channels 0-1 --count 10
python main.py
```

Expected result:

- `serial_monitor.py` initializes `ADS1256`, not `MockAdc`.
- No chip ID mismatch.
- `AD0-AD1` readings are stable and plausible in mV.
- GUI starts and plots live readings.

## Risks

- Wiring may use SPI CE0 instead of the Waveshare manual CS pin BCM `22`.
- Chip ID validation will fail if SPI, power, or CS wiring is incorrect.
- Very low SPI speed matches the sample but may limit throughput.
- `RPi.GPIO` availability depends on Raspberry Pi OS package setup.
- `GAIN=64` clips if the differential input exceeds about `+/-78.125 mV` with `VREF=2.5V`.

## Follow-Up Work

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
