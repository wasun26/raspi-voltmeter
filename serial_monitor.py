"""Terminal serial monitor for Raspberry Pi OS (ADS1256) or mock ADC."""
import argparse
import sys
import time

from config import DEFAULT
from hardware.adc import MockAdc

try:
    from hardware.adc import ADS1256
except Exception:
    ADS1256 = None


def create_adc(adc_cfg, use_mock: bool):
    if use_mock:
        return MockAdc(
            amplitude=adc_cfg.get("mock_amplitude", 1.5),
            offset=adc_cfg.get("mock_offset", 1.5),
            vref=adc_cfg.get("vref", 2.5),
            gain=adc_cfg.get("gain", 1),
            single_ended=adc_cfg.get("single_ended", True),
            sample_rate=adc_cfg.get("sample_rate", 20),
        )

    adc_type = adc_cfg.get("type", "auto")
    if adc_type in ("ads1256", "auto") and ADS1256 is not None:
        try:
            return ADS1256(
                spi_bus=adc_cfg.get("spi_bus", 0),
                spi_device=adc_cfg.get("spi_device", 0),
                drdy_pin=adc_cfg.get("drdy_pin", 17),
                reset_pin=adc_cfg.get("reset_pin", 18),
                cs_pin=adc_cfg.get("cs_pin", 22),
                vref=adc_cfg.get("vref", 2.5),
                gain=adc_cfg.get("gain", 1),
                data_rate=adc_cfg.get("data_rate", 1000),
                single_ended=adc_cfg.get("single_ended", True),
                spi_hz=adc_cfg.get("spi_hz", 20000),
                validate_chip_id=adc_cfg.get("validate_chip_id", True),
                expected_chip_id=adc_cfg.get("expected_chip_id", 3),
            )
        except RuntimeError:
            if adc_type == "ads1256":
                raise

    if adc_type in ("mock", "auto"):
        return MockAdc(
            amplitude=adc_cfg.get("mock_amplitude", 1.5),
            offset=adc_cfg.get("mock_offset", 1.5),
            vref=adc_cfg.get("vref", 2.5),
            gain=adc_cfg.get("gain", 1),
            single_ended=adc_cfg.get("single_ended", True),
            sample_rate=adc_cfg.get("sample_rate", 20),
        )

    raise RuntimeError(
        "ADS1256 requires spidev and RPi.GPIO on Raspberry Pi OS")


def select_unit(full_scale_v: float, unit: str):
    if unit and unit != "auto":
        if unit == "uV":
            return "uV", 1_000_000.0, 0
        if unit == "mV":
            return "mV", 1_000.0, 3
        return "V", 1.0, 6
    if full_scale_v <= 0.01:
        return "uV", 1_000_000.0, 0
    if full_scale_v <= 1.0:
        return "mV", 1_000.0, 4
    return "V", 1.0, 6


def parse_channel(token: str):
    token = token.strip()
    if not token:
        raise ValueError("Empty channel")
    for sep in ("-", ":", "/"):
        if sep in token:
            left, right = token.split(sep, 1)
            return (int(left.strip()), int(right.strip()))
    return int(token)


def format_channel(channel) -> str:
    if isinstance(channel, (tuple, list)) and len(channel) == 2:
        return f"AD{channel[0]}-AD{channel[1]}"
    return f"CH{channel}"


def main():
    parser = argparse.ArgumentParser(
        description="Serial monitor for ADC readings")
    parser.add_argument(
        "--rate", type=float, default=DEFAULT.get("sample_rate", 20), help="Sample rate (Hz)")
    default_channels = DEFAULT.get("channels", [0])
    default_channels_text = ",".join(
        f"{ch[0]}-{ch[1]}" if isinstance(ch, (tuple, list)) and len(ch) == 2 else str(ch)
        for ch in default_channels
    )
    parser.add_argument("--channels", type=str, default=default_channels_text,
                        help="Comma-separated channels. Use 0 for single-ended or 0-1 for differential AD0-AD1")
    parser.add_argument("--averaging", type=int,
                        default=DEFAULT.get("averaging", 1), help="Averaging count")
    parser.add_argument("--unit", type=str, default="auto", choices=["auto", "V", "mV", "uV"],
                        help="Display unit")
    parser.add_argument("--mock", action="store_true",
                        help="Force MockAdc (for non-RPi testing)")
    parser.add_argument("--count", type=int, default=0,
                        help="Number of samples to read (0=run forever)")
    args = parser.parse_args()

    adc_cfg = dict(DEFAULT.get("adc", {}))
    adc_cfg["sample_rate"] = args.rate
    channels = [parse_channel(x) for x in args.channels.split(",") if x.strip()]

    adc = create_adc(adc_cfg, use_mock=args.mock)
    if hasattr(adc, "set_sample_rate"):
        adc.set_sample_rate(args.rate)

    vref = float(getattr(adc, "vref", 2.5))
    gain = float(getattr(adc, "gain", 1))
    single_ended = bool(getattr(adc, "single_ended", True))
    full_scale = vref / max(gain, 1.0)
    if not single_ended:
        full_scale *= 2.0
    unit, scale, decimals = select_unit(full_scale, args.unit)
    fs_scaled = full_scale * scale

    print(
        f"ADC: {adc.__class__.__name__} | Rate: {args.rate} Hz | Channels: {', '.join(format_channel(ch) for ch in channels)}")
    if single_ended:
        range_text = f"0..{fs_scaled:.{decimals}f} {unit}"
    else:
        range_text = f"-{fs_scaled:.{decimals}f}..+{fs_scaled:.{decimals}f} {unit}"
    print(f"Gain: {gain} | Vref: {vref} V | Range: {range_text} | Unit: {unit}")
    print("Press Ctrl+C to stop.\n")

    period = 1.0 / args.rate if args.rate > 0 else 0.1
    count = 0
    try:
        while True:
            ts = time.time()
            readings = []
            for ch in channels:
                if args.averaging <= 1:
                    v = adc.read_voltage(ch)
                else:
                    s = 0.0
                    for _ in range(args.averaging):
                        s += adc.read_voltage(ch)
                    v = s / args.averaging
                readings.append((ch, v))

            parts = [
                f"{format_channel(ch)}: {v * scale:.{decimals}f} {unit}" for ch, v in readings]
            print(f"{ts:.3f} | " + " | ".join(parts))

            count += 1
            if args.count > 0 and count >= args.count:
                break

            elapsed = time.time() - ts
            to_sleep = period - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
