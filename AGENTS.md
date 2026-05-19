# Agents

Guidelines for automated agents working in this repository.

## Scope

- Prioritize Raspberry Pi OS compatibility.
- Keep ADS1256 behavior aligned with the Waveshare Python sample when practical.
- Prefer safe defaults: `adc.type = "auto"` should fall back to `MockAdc` when hardware is unavailable.
- Keep UI changes simple, readable, and consistent with the existing PyQt6 app.

## Hardware

- Hardware access stays isolated in `hardware/`.
- The real ADC implementation is `ADS1256` in `hardware/adc.py`.
- The ADS1256 driver uses `spidev` and `RPi.GPIO`, matching the Waveshare sample style:
  - `spidev.SpiDev(0, 0)`
  - `SPI.writebytes(...)` / `SPI.readbytes(...)`
  - manual GPIO chip select on BCM `22`
  - DRDY on BCM `17` with `GPIO.PUD_UP`
  - RESET on BCM `18`
  - SPI speed `20000` Hz and mode `0b01`
- Keep mock behavior available for non-Raspberry Pi environments.

## Coding Conventions

- Use plain Python 3 code and avoid heavy frameworks.
- Configuration lives in `config.py`.
- UI logic stays in `gui/`.
- Acquisition/timing logic stays in `core/`.
- Do not add large binary files to the repo.

## Testing

- Use `serial_monitor.py` for terminal-only validation.
- Use mock mode for development and non-Raspberry Pi validation:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

- Use auto mode on Raspberry Pi OS to validate ADS1256 while preserving mock fallback:

```bash
python serial_monitor.py --rate 10 --channels 0 --count 10
```

## Notes

- ADS1256 hardware mode requires `spidev`, `RPi.GPIO`, SPI enabled, and correct wiring.
- `requirements.txt` is portable and does not include Raspberry Pi-only packages.
- If changing ADS1256 defaults, update `README.md`, `SETUP.md`, and `PLANNING.md`.
