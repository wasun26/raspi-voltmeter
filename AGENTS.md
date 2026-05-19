# Agents

Guidelines for automated agents working in this repository.

## Scope

- Focus on Raspberry Pi OS compatibility first.
- Prefer safe defaults (mock ADC fallback) when hardware is unavailable.
- Keep UI changes simple and readable.

## Coding Conventions

- Use plain Python 3 code (no heavy frameworks).
- Keep hardware access isolated in `hardware/`.
- UI logic stays in `gui/`.
- Configuration lives in `config.py`.

## Testing

- Use `serial_monitor.py` for terminal-only validation.
- Prefer mock mode for non-RPi environments.

## Notes

- ADS1256 requires `spidev` and `RPi.GPIO` on Raspberry Pi OS.
- Avoid adding large binary files to the repo.
