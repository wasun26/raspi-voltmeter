import sys
from PyQt6.QtWidgets import QApplication

from config import DEFAULT
from hardware.adc import MockAdc
from core.acquisition import AcquisitionManager
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
            vref=adc_cfg.get("vref", 2.5),
            gain=adc_cfg.get("gain", 1),
            single_ended=adc_cfg.get("single_ended", True),
            sample_rate=DEFAULT.get("sample_rate", 20),
        )

    raise ValueError(f"Unsupported ADC type: {adc_type}")


def main():
    adc = create_adc(DEFAULT.get("adc", {}))
    print(f"[main] ADC in use: {adc.__class__.__name__}")
    acq = AcquisitionManager(
        adc_device=adc,
        channels=DEFAULT.get("channels", [0]),
        sample_rate=DEFAULT.get("sample_rate", 20),
        averaging=DEFAULT.get("averaging", 1),
    )

    print("[main] Before QApplication()")
    app = QApplication(sys.argv)
    print("[main] After QApplication()")
    win = MainWindow(
        acquisition_manager=acq,
        plot_window_sec=DEFAULT.get("plot_window_sec", 60),
        plot_max_points=DEFAULT.get("plot_max_points", 2000),
        log_enabled=DEFAULT.get("log_enabled", True),
        log_dir=DEFAULT.get("log_dir", "logs"),
    )
    win.show()

    acq.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
