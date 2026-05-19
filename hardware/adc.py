"""Hardware ADC abstractions and a mock ADC for testing."""
import time
import math
import random


class AdcDevice:
    """Base class for ADC devices."""

    def read_voltage(self, channel: int = 0) -> float:
        """Read a single voltage from the given channel in volts."""
        raise NotImplementedError()


class MockAdc(AdcDevice):
    """Mock ADC emitting a low-frequency sine wave plus small noise.
    
    Can simulate error conditions for testing error handling.
    """

    def __init__(self, amplitude: float = 1.5, offset: float = 1.5, freq: float = 0.25,
                 error_mode: str = "normal", error_rate: float = 0.0):
        """Initialize mock ADC.
        
        Args:
            amplitude: Sine wave amplitude (V)
            offset: DC offset (V)
            freq: Sine wave frequency (Hz)
            error_mode: "normal", "always_error", "random", or "stuck"
            error_rate: For random mode, probability of error (0.0-1.0)
        """
        self.amp = amplitude
        self.offset = offset
        self.freq = freq
        self.error_mode = error_mode.lower()
        self.error_rate = error_rate
        self._t0 = time.time()
        self._error_counter = 0

    def read_voltage(self, channel: int = 0) -> float:
        """Read voltage, possibly with simulated error."""
        # Check error conditions
        if self.error_mode == "always_error":
            self._error_counter += 1
            raise IOError(f"ADC Hardware Error (simulated) on channel {channel}")
        
        if self.error_mode == "random" and random.random() < self.error_rate:
            self._error_counter += 1
            raise IOError(f"ADC Communication Error (simulated, #{self._error_counter})")
        
        if self.error_mode == "stuck":
            # Return a stuck value
            return self.offset
        
        # Normal operation: sine wave + noise
        t = time.time() - self._t0
        return self.offset + self.amp * math.sin(2 * math.pi * self.freq * t) + (random.random() - 0.5) * 0.005


class ADS1256(AdcDevice):
    """ADS1256 24-bit ADC driver for Waveshare High-Precision AD/DA Board (SPI)."""

    REG_STATUS = 0x00
    REG_MUX = 0x01
    REG_ADCON = 0x02
    REG_DRATE = 0x03

    CMD_WAKEUP = 0x00
    CMD_RDATA = 0x01
    CMD_RREG = 0x10
    CMD_WREG = 0x50
    CMD_SYNC = 0xFC
    CMD_RESET = 0xFE

    GAIN_MAP = {
        1: 0x00,
        2: 0x01,
        4: 0x02,
        8: 0x03,
        16: 0x04,
        32: 0x05,
        64: 0x06,
    }

    DRATE_MAP = {
        30000: 0xF0,
        15000: 0xE0,
        7500: 0xD0,
        3750: 0xC0,
        2000: 0xB0,
        1000: 0xA1,
        500: 0x92,
        100: 0x82,
        60: 0x72,
        50: 0x63,
        30: 0x53,
        25: 0x43,
        15: 0x33,
        10: 0x23,
        5: 0x13,
        2.5: 0x03,
    }

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        drdy_pin: int = 17,
        reset_pin: int = 18,
        vref: float = 2.5,
        gain: int = 1,
        data_rate: float = 1000,
        single_ended: bool = True,
        spi_hz: int = 1000000,
    ):
        try:
            import spidev
            import RPi.GPIO as GPIO
        except Exception as exc:
            raise RuntimeError("ADS1256 requires spidev and RPi.GPIO on Raspberry Pi OS") from exc

        self.GPIO = GPIO
        self.vref = float(vref)
        self.gain = int(gain)
        self.data_rate = float(data_rate)
        self.single_ended = bool(single_ended)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_hz
        self.spi.mode = 0x01

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(drdy_pin, GPIO.IN)
        GPIO.setup(reset_pin, GPIO.OUT, initial=GPIO.HIGH)

        self.drdy_pin = drdy_pin
        self.reset_pin = reset_pin

        self._reset()
        self._configure()

    def _reset(self):
        self.GPIO.output(self.reset_pin, self.GPIO.LOW)
        time.sleep(0.01)
        self.GPIO.output(self.reset_pin, self.GPIO.HIGH)
        time.sleep(0.05)
        self.spi.xfer2([self.CMD_RESET])
        time.sleep(0.05)

    def _wait_drdy(self, timeout: float = 1.0):
        start = time.time()
        while self.GPIO.input(self.drdy_pin) == 1:
            if time.time() - start > timeout:
                raise TimeoutError("ADS1256 DRDY timeout")
            time.sleep(0.0005)

    def _write_reg(self, reg: int, value: int):
        self.spi.xfer2([self.CMD_WREG | reg, 0x00, value & 0xFF])
        time.sleep(0.001)

    def _read_reg(self, reg: int) -> int:
        self.spi.xfer2([self.CMD_RREG | reg, 0x00])
        time.sleep(0.001)
        return self.spi.xfer2([0xFF])[0]

    def _configure(self):
        gain_code = self.GAIN_MAP.get(self.gain, 0x00)
        rate_code = self.DRATE_MAP.get(self.data_rate, 0xA1)

        # STATUS: enable buffer (bit 1) for better input impedance
        self._write_reg(self.REG_STATUS, 0x02)
        # MUX: default AIN0-AINCOM
        self._write_reg(self.REG_MUX, 0x08)
        # ADCON: gain setting
        self._write_reg(self.REG_ADCON, gain_code)
        # DRATE: data rate
        self._write_reg(self.REG_DRATE, rate_code)

    def _set_channel(self, channel):
        if isinstance(channel, (tuple, list)) and len(channel) == 2:
            ain_p, ain_n = int(channel[0]), int(channel[1])
            mux = ((ain_p & 0x07) << 4) | (ain_n & 0x07)
        else:
            ch = int(channel)
            if self.single_ended:
                mux = ((ch & 0x07) << 4) | 0x08
            else:
                mux = ((ch & 0x07) << 4) | 0x00

        self._write_reg(self.REG_MUX, mux)
        self.spi.xfer2([self.CMD_SYNC])
        time.sleep(0.001)
        self.spi.xfer2([self.CMD_WAKEUP])
        time.sleep(0.001)

    def _read_raw(self) -> int:
        self._wait_drdy()
        self.spi.xfer2([self.CMD_RDATA])
        time.sleep(0.001)
        data = self.spi.xfer2([0xFF, 0xFF, 0xFF])
        raw = (data[0] << 16) | (data[1] << 8) | data[2]
        if raw & 0x800000:
            raw -= 1 << 24
        return raw

    def read_voltage(self, channel: int = 0) -> float:
        self._set_channel(channel)
        raw = self._read_raw()
        full_scale = 0x7FFFFF
        return (raw / full_scale) * (self.vref / self.gain)
