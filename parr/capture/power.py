"""Battery and external-power state of the Pi's UPS, for the status endpoint.

Only the Geekworm X728 is supported. Its fuel gauge is a MAX17040-class chip
at I2C 0x36 and its power-loss pin is BCM 6; the maths below is Geekworm's
own (``sample/x728-v2.x-bat.py``), so the number shown on the Stick matches
what their tools print.

Hardware access is injected: ``bus`` is anything with ``read_word_data`` and
``pld_is_high`` is any callable. Tests use fakes; ``build_ups`` (Task 4) wires
smbus2 and gpiozero for the real thing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

X728_GAUGE_ADDRESS = 0x36
X728_PLD_PIN = 6
_REG_VCELL = 0x02
_REG_SOC = 0x04


class PowerError(Exception):
    """The UPS could not be read."""


@dataclass(frozen=True)
class PowerStatus:
    percent: int
    voltage_mv: int
    external_power: bool


def decode_word(raw: int) -> int:
    """SMBus returns the 16-bit register little-endian; the gauge stores big-endian."""
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


class X728Ups:
    def __init__(self, bus, pld_is_high: Callable[[], bool], address: int = X728_GAUGE_ADDRESS):
        self._bus = bus
        self._pld_is_high = pld_is_high
        self._address = address

    def read(self) -> PowerStatus:
        try:
            vcell = decode_word(self._bus.read_word_data(self._address, _REG_VCELL))
            soc = decode_word(self._bus.read_word_data(self._address, _REG_SOC))
        except OSError as exc:
            raise PowerError(
                f"cannot read the X728 fuel gauge at 0x{self._address:02x}: {exc}. "
                "Is I2C enabled and the shield fitted? Check with: sudo i2cdetect -y 1"
            ) from exc
        voltage_mv = round(vcell * 1.25 / 16)
        percent = min(soc // 256, 100)
        external = not self._pld_is_high()
        return PowerStatus(percent=percent, voltage_mv=voltage_mv, external_power=external)
