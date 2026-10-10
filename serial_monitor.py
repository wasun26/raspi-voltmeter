"""Terminal monitor for Raspberry Pi OS ADS1256 hardware or mock ADC."""
import argparse
import signal
import sys
import threading
import time

from config import DEFAULT, load_recording_settings
from hardware.adc import MockAdc
from core.recording import CsvRecorder

try:
    from hardware.adc import ADS1256
except Exception:
    ADS1256 = None


def create_mock_adc(adc_cfg):
    return MockAdc(
        amplitude=adc_cfg.get("mock_amplitude", 1.5),
        offset=adc_cfg.get("mock_offset", 1.5),
        vref=adc_cfg.get("vref", 2.5),
        gain=adc_cfg.get("gain", 1),
        single_ended=adc_cfg.get("single_ended", True),
        sample_rate=adc_cfg.get("sample_rate", 20),
    )


def create_ads1256(adc_cfg):
    if ADS1256 is None:
        raise RuntimeError("ADS1256 driver requires spidev and RPi.GPIO on Raspberry Pi OS")

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


def create_adc(adc_cfg):
    adc_type = adc_cfg.get("type", "auto")
    if adc_type in ("mock", "auto", "ads1256"):
        pass
    else:
        raise ValueError(f"Unsupported ADC type: {adc_type}")

    if adc_type == "mock":
        return create_mock_adc(adc_cfg), None

    if adc_type == "ads1256":
        try:
            return create_ads1256(adc_cfg), None
        except Exception as exc:
            raise RuntimeError(f"ADS1256 initialization failed: {exc}") from exc

    try:
        return create_ads1256(adc_cfg), None
    except Exception as exc:
        return create_mock_adc(adc_cfg), exc


def parse_bool(value: str) -> bool:
    text = value.strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise argparse.ArgumentTypeError("expected true/false")


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
    try:
        recording_settings = load_recording_settings()
    except Exception as exc:
        print(f"ERROR: could not load recording settings: {exc}", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(
        description="Serial monitor for ADC readings")
    parser.add_argument(
        "--rate", type=float, default=DEFAULT.get("sample_rate", 20), help="Sample rate (Hz)")
    parser.add_argument("--adc", choices=["auto", "ads1256", "mock"], default=None,
                        help="ADC backend. ads1256 requires real Raspberry Pi hardware; auto falls back to mock.")
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
                        help="Force MockAdc (same as --adc mock)")
    parser.add_argument("--gain", type=int, default=None,
                        help="PGA gain override, for example 1, 2, 4, 8, 16, 32, 64")
    parser.add_argument("--data-rate", type=float, default=None,
                        help="ADS1256 data rate override in SPS")
    parser.add_argument("--single-ended", type=parse_bool, default=None,
                        help="Input mode override: true for single-ended, false for differential")
    parser.add_argument("--no-chip-id-check", action="store_true",
                        help="Skip ADS1256 chip ID validation while debugging SPI/CS wiring")
    parser.add_argument("--count", type=int, default=0,
                        help="Number of samples to read (0=run forever)")
    parser.add_argument("--log-dir", default=recording_settings["directory"],
                        help="CSV directory (default: logs); each row is flushed and fsynced")
    parser.add_argument("--max-data-lines", type=int, default=recording_settings["max_data_lines"],
                        help="Data rows per CSV file, excluding header (0=no limit)")
    parser.add_argument("--file-prefix", default=recording_settings["file_prefix"],
                        help="CSV filename prefix")
    parser.add_argument("--min-free-mb", type=int, default=recording_settings["min_free_mb"],
                        help="Stop below this free space in MiB (0=no reserve)")
    parser.add_argument("--daily-rotation", type=parse_bool, default=recording_settings["rotate_daily"],
                        help="Start a new file daily: true/false")
    parser.add_argument("--no-log", action="store_true",
                        help="Disable CSV recording")
    parser.add_argument("--quiet", action="store_true",
                        help="Print startup/errors only, suitable for unattended recording")
    args = parser.parse_args()
    if args.rate <= 0 or args.averaging < 1 or args.count < 0:
        parser.error("rate and averaging must be positive; count must be nonnegative")

    adc_cfg = dict(DEFAULT.get("adc", {}))
    adc_cfg["sample_rate"] = args.rate
    if args.adc is not None:
        adc_cfg["type"] = args.adc
    if args.mock:
        adc_cfg["type"] = "mock"
    if args.gain is not None:
        adc_cfg["gain"] = args.gain
    if args.data_rate is not None:
        adc_cfg["data_rate"] = args.data_rate
    if args.single_ended is not None:
        adc_cfg["single_ended"] = args.single_ended
    if args.no_chip_id_check:
        adc_cfg["validate_chip_id"] = False
    channels = [parse_channel(x) for x in args.channels.split(",") if x.strip()]
    if not channels:
        parser.error("at least one channel is required")

    adc = None
    try:
        adc, fallback_error = create_adc(adc_cfg)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        if args.data_rate is not None and hasattr(adc, "set_data_rate"):
            adc.set_data_rate(args.data_rate)
        elif hasattr(adc, "set_sample_rate"):
            adc.set_sample_rate(args.rate)
    except Exception as exc:
        if hasattr(adc, "close"):
            adc.close()
        print(f"ERROR: ADC rate configuration failed: {exc}", file=sys.stderr)
        return 1

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
    if fallback_error is not None:
        print(f"Auto mode fallback: ADS1256 unavailable ({fallback_error})")
    if single_ended:
        range_text = f"0..{fs_scaled:.{decimals}f} {unit}"
    else:
        range_text = f"-{fs_scaled:.{decimals}f}..+{fs_scaled:.{decimals}f} {unit}"
    data_rate = getattr(adc, "data_rate", None)
    rate_text = f" | ADS1256 data rate: {data_rate:g} SPS" if data_rate is not None else ""
    mode_text = "single-ended" if single_ended else "differential"
    print(f"Mode: {mode_text} | Gain: {gain:g} | Vref: {vref:g} V | Range: {range_text} | Unit: {unit}{rate_text}")
    print("Press Ctrl+C to stop.\n")

    period = 1.0 / args.rate if args.rate > 0 else 0.1
    count = 0
    recorder = None
    recording_failed = False
    stop_requested = threading.Event()
    old_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.signal(sig, lambda *_: stop_requested.set())
    try:
        if DEFAULT.get("log_enabled", True) and not args.no_log:
            recording_failed = True
            recorder = CsvRecorder(args.log_dir, channels, adc, args.averaging,
                                   max_data_lines=args.max_data_lines, file_prefix=args.file_prefix,
                                   rotate_daily=args.daily_rotation, min_free_mb=args.min_free_mb)
            recording_failed = False
            print(f"CSV directory: {recorder.directory} (flush + fsync every sample)")
        while not stop_requested.is_set():
            started = time.monotonic()
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

            if recorder is not None:
                recording_failed = True
                recorder.write(ts, dict(readings))
                recording_failed = False
                if count == 0:
                    print(f"CSV file: {recorder.path}")

            parts = [
                f"{format_channel(ch)}: {v * scale:.{decimals}f} {unit}" for ch, v in readings]
            if not args.quiet:
                print(f"{ts:.3f} | " + " | ".join(parts))

            count += 1
            if args.count > 0 and count >= args.count:
                break

            elapsed = time.monotonic() - started
            to_sleep = period - elapsed
            if to_sleep > 0:
                stop_requested.wait(to_sleep)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        operation = "recording" if recording_failed else "read"
        print(f"\nERROR: {operation} failed; acquisition stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        try:
            if recorder is not None:
                recorder.close()
        finally:
            if adc is not None and hasattr(adc, "close"):
                adc.close()

    if recorder is not None:
        print(f"Saved {recorder.saved_count} samples. Last CSV: {recorder.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
