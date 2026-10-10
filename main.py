import sys
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QApplication

from config import DEFAULT, load_recording_settings
from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
from core.recording import CsvRecorder
from gui.main_window import MainWindow

try:
    from hardware.adc import ADS1256
except Exception:
    ADS1256 = None


def create_adc(adc_cfg):
    adc_type = adc_cfg.get("type", "mock")
    if adc_type in ("ads1256", "auto"):
        if ADS1256 is not None:
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
        if adc_type == "ads1256":
            raise RuntimeError(
                "ADS1256 driver requires spidev and RPi.GPIO on Raspberry Pi OS")

    if adc_type in ("mock", "auto"):
        return MockAdc(
            amplitude=adc_cfg.get("mock_amplitude", 1.5),
            offset=adc_cfg.get("mock_offset", 1.5),
            vref=adc_cfg.get("vref", 2.5),
            gain=adc_cfg.get("gain", 1),
            single_ended=adc_cfg.get("single_ended", True),
            sample_rate=DEFAULT.get("sample_rate", 20),
        )

    raise ValueError(f"Unsupported ADC type: {adc_type}")


def main():
    QLocale.setDefault(QLocale.c())
    recording_settings = load_recording_settings()
    adc = create_adc(DEFAULT.get("adc", {}))
    print(f"[main] ADC in use: {adc.__class__.__name__}")
    recorder = CsvRecorder(
        recording_settings.pop("directory"), DEFAULT.get("channels", [0]), adc,
        DEFAULT.get("averaging", 1),
        **recording_settings,
    ) if DEFAULT.get("log_enabled", True) else None
    acq = AcquisitionManager(
        adc_device=adc,
        channels=DEFAULT.get("channels", [0]),
        sample_rate=DEFAULT.get("sample_rate", 20),
        averaging=DEFAULT.get("averaging", 1),
        recorder=recorder,
    )

    print("[main] Before QApplication()")
    app = QApplication(sys.argv)
    print("[main] After QApplication()")
    win = MainWindow(
        acquisition_manager=acq,
        plot_window_sec=DEFAULT.get("plot_window_sec", 60),
        plot_max_points=DEFAULT.get("plot_max_points", 2000),
        collection_mode=DEFAULT.get("collection_mode_on_start", False),
        collection_ui_refresh_ms=DEFAULT.get("collection_ui_refresh_ms", 3000),
    )
    win.show()

    acq.start()
    try:
        result = app.exec()
    finally:
        acq.stop()
        if acq.recorder is not None:
            acq.recorder.close()
        if hasattr(adc, "close"):
            adc.close()
    sys.exit(result)


if __name__ == "__main__":
    main()
