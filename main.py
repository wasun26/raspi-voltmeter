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
                    vref=adc_cfg.get("vref", 2.5),
                    gain=adc_cfg.get("gain", 1),
                    data_rate=adc_cfg.get("data_rate", 1000),
                    single_ended=adc_cfg.get("single_ended", True),
                )
            except RuntimeError:
                if adc_type == "ads1256":
                    raise
        if adc_type == "ads1256":
            raise RuntimeError("ADS1256 driver requires spidev and RPi.GPIO on Raspberry Pi OS")

    if adc_type in ("mock", "auto"):
        return MockAdc()

    raise ValueError(f"Unsupported ADC type: {adc_type}")


def main():
    adc = create_adc(DEFAULT.get("adc", {}))
    acq = AcquisitionManager(
        adc_device=adc,
        channels=DEFAULT.get("channels", [0]),
        sample_rate=DEFAULT.get("sample_rate", 20),
        averaging=DEFAULT.get("averaging", 1),
    )

    app = QApplication(sys.argv)
    win = MainWindow(acquisition_manager=acq)
    win.show()

    acq.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
