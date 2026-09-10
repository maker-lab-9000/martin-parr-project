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

import threading
import time
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


class PowerMonitor:
    """Polls a provider on its own thread; ``snapshot`` never touches hardware."""

    max_age_s: float = 60.0

    def __init__(
        self,
        provider,
        interval_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._provider = provider
        self._interval_s = interval_s
        self._clock = clock
        self._lock = threading.Lock()
        self._status: PowerStatus | None = None
        self._read_at: float | None = None
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self._sleep = (
            sleep if sleep is not None else (lambda seconds: self._closed.wait(seconds))
        )

    def poll_once(self) -> None:
        try:
            status = self._provider.read()
        except PowerError as exc:
            with self._lock:
                self.last_error = str(exc)
            return
        with self._lock:
            self._status = status
            self._read_at = self._clock()
            self.last_error = None

    def snapshot(self) -> PowerStatus | None:
        with self._lock:
            if self._status is None or self._read_at is None:
                return None
            if self._clock() - self._read_at > self.max_age_s:
                return None
            return self._status

    def _poll_and_wait(self) -> None:
        self.poll_once()
        self._sleep(self._interval_s)

    def _run(self) -> None:
        while not self._closed.is_set():
            self._poll_and_wait()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="parr-power", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


UPS_CHOICES = ("none", "x728")


def _open_smbus(number: int):
    import smbus2  # lazy: only present on the Pi, only needed with --ups x728

    return smbus2.SMBus(number)


def _open_input_pin(number: int) -> Callable[[], bool]:
    from gpiozero import DigitalInputDevice  # lazy, same reason

    pin = DigitalInputDevice(number, pull_up=None, active_state=True)
    return lambda: bool(pin.value)


def build_ups(name: str, *, open_bus=None, open_pin=None) -> PowerMonitor | None:
    """Return a started-ready PowerMonitor for ``name``, or None for "none"."""
    if name == "none":
        return None
    if name != "x728":
        raise PowerError(f"unknown UPS {name!r}; choose one of {', '.join(UPS_CHOICES)}")
    open_bus = open_bus or _open_smbus
    open_pin = open_pin or _open_input_pin
    try:
        bus = open_bus(1)
        pld_is_high = open_pin(X728_PLD_PIN)
    except ImportError as exc:
        raise PowerError(
            f"--ups x728 needs python3-smbus2 and python3-gpiozero ({exc}). They are "
            "present on the Pi image; this machine does not have them"
        ) from exc
    except (FileNotFoundError, PermissionError) as exc:
        raise PowerError(
            f"cannot open I2C bus 1 ({exc}). Enable it with: sudo raspi-config nonint do_i2c 0, "
            "reboot, and make sure the service user is in the i2c group"
        ) from exc
    return PowerMonitor(X728Ups(bus, pld_is_high=pld_is_high))
