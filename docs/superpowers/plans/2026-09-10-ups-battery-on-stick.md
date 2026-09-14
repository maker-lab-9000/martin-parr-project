# UPS Battery on the Stick Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the Pi's X728 UPS battery level and external-power state on the StickS3, in a badge next to the Stick's own battery badge.

**Architecture:** The Pi reads the X728 fuel gauge (I2C `0x36`) and power-loss pin (BCM 6) in a background poller inside `parr-capture`, and publishes the result as a `pi_battery` object in the existing `GET /v1/status` payload. The Stick already polls that endpoint twice a second; a small Arduino-free parser extracts the new fields and feeds a second `BatteryMonitor`, and the display draws a second badge in the bottom-left corner. Hardware access on the Pi is behind an injected interface so every decision is unit-tested with fakes.

**Tech Stack:** Python 3.11+, `smbus2` and `gpiozero` (both already on the Pi), pytest; C++17 with PlatformIO, Unity native tests, M5Unified.

**Spec:** `docs/x728-ups.md` (hardware, pins, registers, prerequisites). Base branch: `feature/stick-battery-level`, which provides `BatteryMonitor`, `StickDisplay::setBatteryLabel()` and the badge layout this plan extends. Do the prerequisite in `docs/x728-ups.md` section 4 first: I2C enabled and `i2cdetect -y 1` showing `36`.

## Global Constraints

- Python: no new runtime dependency in `pyproject.toml`; `smbus2` and `gpiozero` are imported lazily and only when `--ups x728` is given, so Mac tests and the `--fake` path never need them.
- The fuel gauge decoding is exactly Geekworm's: VCELL register `0x02`, volts = big-endian word × 1.25 / 1000 / 16; SOC register `0x04`, percent = big-endian word / 256, clamped to 100. Pin 6: `0` means external power present.
- `GET /v1/status` stays backward compatible: every existing key unchanged; new key `pi_battery` is an object or `null`.
- Firmware: nothing in `capture_client.*` changes. New parsing code has no Arduino dependency and is covered by the `native` env.
- Badge text format matches the Stick badge: `87%`, `87%+` with external power, `--%` unknown; prefixed `Pi ` for the Pi badge.
- Ruff clean (`E, F, I, B, UP`, line length 100). Commit after every task.

---

### Task 1: Fuel gauge decoding and the X728 provider

**Files:**
- Create: `parr/capture/power.py`
- Test: `tests/test_power.py`

**Interfaces:**
- Consumes: nothing in the repo.
- Produces:
  - `@dataclass(frozen=True) PowerStatus(percent: int, voltage_mv: int, external_power: bool)`
  - `class PowerError(Exception)`
  - `decode_word(raw: int) -> int` (byte-swap of a little-endian SMBus word)
  - `class X728Ups:` `__init__(self, bus, pld_is_high: Callable[[], bool], address: int = 0x36)`; `read(self) -> PowerStatus`. `bus` needs only `read_word_data(address, register) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_power.py
"""The X728 fuel gauge and power-loss pin, decoded exactly as Geekworm's scripts do."""

import pytest

from parr.capture.power import PowerError, PowerStatus, X728Ups, decode_word


class FakeBus:
    def __init__(self, words: dict[int, int]):
        self.words = words
        self.reads: list[tuple[int, int]] = []

    def read_word_data(self, address: int, register: int) -> int:
        self.reads.append((address, register))
        return self.words[register]


def test_decode_word_swaps_the_smbus_little_endian_bytes():
    # SMBus hands back 0x3412 for a chip that stored big-endian 0x1234.
    assert decode_word(0x3412) == 0x1234


def test_x728_reads_voltage_and_charge_from_registers_2_and_4():
    # VCELL 0xC800 big-endian -> SMBus 0x00C8 -> 0xC800 * 1.25 / 16 mV = 4000 mV.
    # SOC 0x5780 -> 0x5780 / 256 = 87.5 % -> 87.
    bus = FakeBus({0x02: 0x00C8, 0x04: 0x8057})
    ups = X728Ups(bus, pld_is_high=lambda: False)

    status = ups.read()

    assert status == PowerStatus(percent=87, voltage_mv=4000, external_power=True)
    assert bus.reads == [(0x36, 0x02), (0x36, 0x04)]


def test_soc_above_one_hundred_is_clamped_like_geekworm_does():
    bus = FakeBus({0x02: 0x00C8, 0x04: 0x0068})  # 0x6800 / 256 = 104 %
    assert X728Ups(bus, pld_is_high=lambda: False).read().percent == 100


def test_pld_pin_high_means_running_on_battery():
    bus = FakeBus({0x02: 0x00C8, 0x04: 0x8057})
    assert X728Ups(bus, pld_is_high=lambda: True).read().external_power is False


def test_bus_errors_become_power_errors_with_the_i2c_remedy():
    class BrokenBus:
        def read_word_data(self, address, register):
            raise OSError(121, "Remote I/O error")

    with pytest.raises(PowerError, match="i2cdetect"):
        X728Ups(BrokenBus(), pld_is_high=lambda: False).read()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_power.py`
Expected: `ModuleNotFoundError: No module named 'parr.capture.power'`

- [ ] **Step 3: Write the minimal implementation**

```python
# parr/capture/power.py
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
        return PowerStatus(percent=percent, voltage_mv=voltage_mv, external_power=not self._pld_is_high())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_power.py && .venv/bin/ruff check parr tests`
Expected: `5 passed`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add parr/capture/power.py tests/test_power.py
git commit -m "Decode the X728 fuel gauge and power-loss pin"
```

---

### Task 2: Background poller with a cached snapshot

**Files:**
- Modify: `parr/capture/power.py`
- Test: `tests/test_power.py`

**Interfaces:**
- Consumes: `PowerStatus`, `PowerError`, and any object with `read() -> PowerStatus` from Task 1.
- Produces: `class PowerMonitor:` `__init__(self, provider, interval_s: float = 10.0, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep)`; `poll_once(self) -> None`; `snapshot(self) -> PowerStatus | None` (None until the first successful read, or after `max_age_s` without one); `start(self) -> None`; `close(self) -> None`; attribute `max_age_s: float = 60.0`; `last_error: str | None`.

The HTTP handler must never block on I2C, so reads happen on a thread and the handler only copies the last value. A stale value is worse than none: after 60 s without a successful read the snapshot returns `None` and the Stick shows `Pi --%`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_power.py
from parr.capture.power import PowerMonitor


class ScriptedProvider:
    def __init__(self, results):
        self.results = list(results)

    def read(self):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_snapshot_is_none_before_the_first_successful_read():
    monitor = PowerMonitor(ScriptedProvider([]), clock=FakeClock())
    assert monitor.snapshot() is None


def test_poll_once_stores_the_reading_and_snapshot_returns_it():
    clock = FakeClock()
    reading = PowerStatus(percent=87, voltage_mv=4000, external_power=True)
    monitor = PowerMonitor(ScriptedProvider([reading]), clock=clock)

    monitor.poll_once()

    assert monitor.snapshot() == reading
    assert monitor.last_error is None


def test_a_failed_read_keeps_the_previous_reading_and_records_the_error():
    clock = FakeClock()
    reading = PowerStatus(percent=87, voltage_mv=4000, external_power=True)
    monitor = PowerMonitor(ScriptedProvider([reading, PowerError("gauge missing")]), clock=clock)

    monitor.poll_once()
    monitor.poll_once()

    assert monitor.snapshot() == reading
    assert monitor.last_error == "gauge missing"


def test_a_reading_older_than_max_age_is_not_served():
    clock = FakeClock()
    reading = PowerStatus(percent=87, voltage_mv=4000, external_power=True)
    monitor = PowerMonitor(ScriptedProvider([reading]), clock=clock)
    monitor.poll_once()

    clock.now += monitor.max_age_s + 1

    assert monitor.snapshot() is None


def test_start_polls_on_the_interval_until_closed():
    clock = FakeClock()
    sleeps: list[float] = []
    readings = [PowerStatus(percent=p, voltage_mv=4000, external_power=True) for p in (90, 89, 88)]
    monitor = PowerMonitor(ScriptedProvider(readings), interval_s=10.0, clock=clock, sleep=sleeps.append)
    # Drive the loop body directly instead of a real thread: deterministic and fast.
    for _ in range(3):
        monitor._poll_and_wait()
    monitor.close()

    assert monitor.snapshot().percent == 88
    assert sleeps == [10.0, 10.0, 10.0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_power.py`
Expected: `ImportError: cannot import name 'PowerMonitor'`

- [ ] **Step 3: Write the minimal implementation**

```python
# append to parr/capture/power.py
import threading
import time


class PowerMonitor:
    """Polls a provider on its own thread; ``snapshot`` never touches hardware."""

    max_age_s: float = 60.0

    def __init__(
        self,
        provider,
        interval_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._interval_s = interval_s
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._status: PowerStatus | None = None
        self._read_at: float | None = None
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

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
```

Move the `import threading` and `import time` lines to the top of the module with the other imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_power.py && .venv/bin/ruff check parr tests`
Expected: `10 passed`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add parr/capture/power.py tests/test_power.py
git commit -m "Poll the UPS on a thread and serve a bounded-age snapshot"
```

---

### Task 3: `pi_battery` in the status payload

**Files:**
- Modify: `parr/capture/remote.py` (`RemoteCaptureServer.__init__` around line 49, `_status_payload` around line 199)
- Test: `tests/test_remote.py`

**Interfaces:**
- Consumes: `PowerStatus` from Task 1.
- Produces: `RemoteCaptureServer(controller, token, listen, power: Callable[[], PowerStatus | None] | None = None)`. Payload key `pi_battery`: `{"percent": int, "voltage_mv": int, "external_power": bool}` or `null`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_remote.py
from parr.capture.power import PowerStatus


def test_status_reports_pi_battery_when_a_power_source_is_configured(tmp_path):
    session = BlockingSession()
    controller = CaptureController(session)
    reading = PowerStatus(percent=87, voltage_mv=4012, external_power=True)
    server = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0), power=lambda: reading)
    server.start()
    try:
        status = _json(server, "GET", "/v1/status")[2]
    finally:
        server.close()
        controller.close()

    assert status["pi_battery"] == {"percent": 87, "voltage_mv": 4012, "external_power": True}
    assert set(status) >= {"instance_id", "ready", "active_capture_id", "last_completed_id"}


def test_status_reports_pi_battery_null_without_a_power_source_or_reading(remote):
    server, _session = remote
    assert _json(server, "GET", "/v1/status")[2]["pi_battery"] is None

    session = BlockingSession()
    controller = CaptureController(session)
    unknown = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0), power=lambda: None)
    unknown.start()
    try:
        assert _json(unknown, "GET", "/v1/status")[2]["pi_battery"] is None
    finally:
        unknown.close()
        controller.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_remote.py -k pi_battery`
Expected: `TypeError: __init__() got an unexpected keyword argument 'power'` and `KeyError: 'pi_battery'`

- [ ] **Step 3: Write the minimal implementation**

In `parr/capture/remote.py`, extend the constructor and payload:

```python
from collections.abc import Callable

from .power import PowerStatus
```

```python
    def __init__(
        self,
        controller: CaptureController,
        token: str,
        listen: tuple[str, int],
        power: Callable[[], PowerStatus | None] | None = None,
    ) -> None:
        if not token:
            raise ValueError("a non-empty remote token is required")
        self._controller = controller
        self._token = token
        # Optional UPS reader. Called on the request thread, so it must be a
        # cheap copy of a cached value (PowerMonitor.snapshot), never an I2C read.
        self._power = power
        ...  # existing body unchanged
```

```python
    def _status_payload(self) -> dict[str, Any]:
        snapshot = self._controller.snapshot()
        battery = self._power() if self._power is not None else None
        return {
            "instance_id": self.instance_id,
            "ready": not snapshot.closed,
            "active_capture_id": snapshot.active_job.request_id if snapshot.active_job else None,
            "last_completed_id": (
                snapshot.last_completed_job.request_id if snapshot.last_completed_job else None
            ),
            "pi_battery": (
                {
                    "percent": battery.percent,
                    "voltage_mv": battery.voltage_mv,
                    "external_power": battery.external_power,
                }
                if battery is not None else None
            ),
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_remote.py && .venv/bin/ruff check parr tests`
Expected: all remote tests pass including the two new ones; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add parr/capture/remote.py tests/test_remote.py
git commit -m "Publish the Pi battery in the status payload"
```

---

### Task 4: `--ups x728` on the command line, wired into the service

**Files:**
- Modify: `parr/capture/power.py` (add `build_ups`)
- Modify: `parr/capture/app.py` (argument parser around line 440; server construction at line 505; shutdown in the `finally` block)
- Modify: `deploy/parr-capture.service.example` (`ExecStart`)
- Modify: `.env.example` (comment only)
- Test: `tests/test_power.py`

**Interfaces:**
- Consumes: `X728Ups`, `PowerMonitor`, `PowerError` from Tasks 1 and 2.
- Produces: `build_ups(name: str, *, open_bus=None, open_pin=None) -> PowerMonitor | None`. `name` is `"none"` or `"x728"`. The two keyword hooks exist for tests; the defaults import `smbus2` and `gpiozero` lazily.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_power.py
from parr.capture.power import build_ups


def test_build_ups_none_returns_no_monitor():
    assert build_ups("none") is None


def test_build_ups_x728_wires_bus_one_address_0x36_and_pin_6():
    opened = {}

    def open_bus(number):
        opened["bus"] = number
        return FakeBus({0x02: 0x00C8, 0x04: 0x8057})

    def open_pin(number):
        opened["pin"] = number
        return lambda: False

    monitor = build_ups("x728", open_bus=open_bus, open_pin=open_pin)
    monitor.poll_once()

    assert opened == {"bus": 1, "pin": 6}
    assert monitor.snapshot().percent == 87


def test_build_ups_x728_explains_a_missing_i2c_bus():
    def open_bus(number):
        raise FileNotFoundError(2, "No such file or directory", "/dev/i2c-1")

    with pytest.raises(PowerError, match="raspi-config nonint do_i2c 0"):
        build_ups("x728", open_bus=open_bus, open_pin=lambda n: (lambda: False))


def test_build_ups_rejects_unknown_names():
    with pytest.raises(PowerError, match="x728"):
        build_ups("apc")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_power.py -k build_ups`
Expected: `ImportError: cannot import name 'build_ups'`

- [ ] **Step 3: Write the minimal implementation**

```python
# append to parr/capture/power.py
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
    except (FileNotFoundError, PermissionError) as exc:
        raise PowerError(
            f"cannot open I2C bus 1 ({exc}). Enable it with: sudo raspi-config nonint do_i2c 0, "
            "reboot, and make sure the service user is in the i2c group"
        ) from exc
    return PowerMonitor(X728Ups(bus, pld_is_high=open_pin(X728_PLD_PIN)))
```

In `parr/capture/app.py`, add the flag next to `--remote-listen`:

```python
    parser.add_argument(
        "--ups", choices=UPS_CHOICES, default="none",
        help="UPS to read the Pi's battery from and publish in /v1/status (default: none)",
    )
```

with `from .power import UPS_CHOICES, PowerError, build_ups` among the imports. After the token check and before the pipeline is built:

```python
    power = None
    try:
        power = build_ups(args.ups)
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if power is not None:
        power.start()
        print(f"Reading the {args.ups} UPS every 10 s.")
```

Pass it to the server: `RemoteCaptureServer(controller, remote_token, args.remote_listen, power=power.snapshot if power else None)`. In the `finally` block, before `remote.close()`, add `if power is not None: power.close()`.

In `deploy/parr-capture.service.example`, append ` --ups x728` to `ExecStart` and add a comment line above it: `# --ups x728 reads the Geekworm X728 fuel gauge for the Stick's Pi-battery badge; drop it on a Pi without the shield.` In `.env.example`, add a comment under `PARR_LISTEN`: `# The service unit's --ups flag selects the UPS (none or x728); see docs/x728-ups.md.`

- [ ] **Step 4: Run the tests and the fake capture path to verify**

Run: `.venv/bin/pytest -q -m 'not slow' && .venv/bin/ruff check . && .venv/bin/parr-capture --fake --no-preview --ups none --help >/dev/null && echo ok`
Expected: full suite passes, ruff clean, `ok`. On a Mac `--ups x728` must fail fast with the I2C remedy: `.venv/bin/parr-capture --fake --no-preview --ups x728; echo "exit $?"` prints `error: cannot open I2C bus 1 ...` and `exit 2` (or `No module named 'smbus2'` if the lazy import fails first; either is a clean exit 2).

- [ ] **Step 5: Commit**

```bash
git add parr/capture/power.py parr/capture/app.py deploy/parr-capture.service.example .env.example tests/test_power.py
git commit -m "Add --ups x728 to publish the Pi battery from the capture service"
```

---

### Task 5: Firmware parser for the Pi battery fields

**Files:**
- Create: `firmware/sticks3/include/status_fields.h`
- Create: `firmware/sticks3/src/status_fields.cpp`
- Create: `firmware/sticks3/test/test_status_fields/test_main.cpp`
- Modify: `firmware/sticks3/platformio.ini` (`[env:native]` `build_src_filter`: add `+<status_fields.cpp>`)

**Interfaces:**
- Consumes: nothing.
- Produces: `struct PiBattery { bool known = false; int percent = -1; bool external_power = false; };` and `PiBattery parsePiBattery(const char* json);`. `known` is false when the key is absent or `null`.

The firmware's existing JSON handling is `String::indexOf` in `main.cpp`, which cannot be unit-tested natively. This parser uses only `<cstring>` and `<cstdlib>`, so the native env covers it.

- [ ] **Step 1: Write the failing tests**

```cpp
// firmware/sticks3/test/test_status_fields/test_main.cpp
#ifdef PIO_UNIT_TESTING
#include <unity.h>
#else
#include <cassert>
#include <cstring>
#define TEST_ASSERT_TRUE(value) assert(value)
#define TEST_ASSERT_FALSE(value) assert(!(value))
#define TEST_ASSERT_EQUAL(expected, actual) assert((expected) == (actual))
#endif

#include "status_fields.h"

namespace {

const char* kWithBattery =
    "{\"instance_id\":\"a9f8ccaf-23a4-403c-8d02-2f20230e9f91\",\"ready\":true,"
    "\"active_capture_id\":null,\"last_completed_id\":null,"
    "\"pi_battery\":{\"percent\":87,\"voltage_mv\":4012,\"external_power\":true}}";

void test_parses_percent_and_external_power_from_the_status_payload(void) {
  const PiBattery battery = parsePiBattery(kWithBattery);
  TEST_ASSERT_TRUE(battery.known);
  TEST_ASSERT_EQUAL(87, battery.percent);
  TEST_ASSERT_TRUE(battery.external_power);
}

void test_null_pi_battery_is_unknown(void) {
  const PiBattery battery = parsePiBattery("{\"ready\":true,\"pi_battery\":null}");
  TEST_ASSERT_FALSE(battery.known);
  TEST_ASSERT_EQUAL(-1, battery.percent);
}

void test_missing_key_is_unknown_for_older_servers(void) {
  const PiBattery battery = parsePiBattery("{\"ready\":true,\"active_capture_id\":null}");
  TEST_ASSERT_FALSE(battery.known);
}

void test_external_power_false_and_spaces_after_colons_are_accepted(void) {
  const PiBattery battery =
      parsePiBattery("{\"pi_battery\": {\"percent\": 5, \"voltage_mv\": 3300, \"external_power\": false}}");
  TEST_ASSERT_TRUE(battery.known);
  TEST_ASSERT_EQUAL(5, battery.percent);
  TEST_ASSERT_FALSE(battery.external_power);
}

void test_percent_outside_zero_to_hundred_is_unknown(void) {
  TEST_ASSERT_FALSE(parsePiBattery("{\"pi_battery\":{\"percent\":250,\"external_power\":true}}").known);
  TEST_ASSERT_FALSE(parsePiBattery("{\"pi_battery\":{\"percent\":-3,\"external_power\":true}}").known);
}

void run_all(void) {
  UNITY_BEGIN();
  RUN_TEST(test_parses_percent_and_external_power_from_the_status_payload);
  RUN_TEST(test_null_pi_battery_is_unknown);
  RUN_TEST(test_missing_key_is_unknown_for_older_servers);
  RUN_TEST(test_external_power_false_and_spaces_after_colons_are_accepted);
  RUN_TEST(test_percent_outside_zero_to_hundred_is_unknown);
  UNITY_END();
}

}  // namespace

#ifdef PIO_UNIT_TESTING
int main(int, char**) { run_all(); return 0; }
#else
int main() { run_all(); return 0; }
#endif
```

Add `+<status_fields.cpp>` to the `[env:native]` `build_src_filter` in `platformio.ini`, after `+<battery_status.cpp>`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pio test -d firmware/sticks3 -e native -f test_status_fields`
Expected: `fatal error: 'status_fields.h' file not found`

- [ ] **Step 3: Write the minimal implementation**

```cpp
// firmware/sticks3/include/status_fields.h
#pragma once

// The Pi's UPS battery as published in GET /v1/status. `known` is false when
// the server has no UPS (`"pi_battery":null`), predates the field, or sent a
// value outside 0..100.
struct PiBattery {
  bool known = false;
  int percent = -1;
  bool external_power = false;
};

// Extracts pi_battery.percent and pi_battery.external_power from the status
// JSON. Deliberately small: the payload is produced by our own server, keys
// are unique, and this must run under the native tests without Arduino.
PiBattery parsePiBattery(const char* json);
```

```cpp
// firmware/sticks3/src/status_fields.cpp
#include "status_fields.h"

#include <cstdlib>
#include <cstring>

namespace {

// Returns a pointer just past `"key":` (any spaces after the colon skipped), or nullptr.
const char* valueOf(const char* json, const char* key) {
  char quoted[48];
  std::snprintf(quoted, sizeof(quoted), "\"%s\"", key);
  const char* at = std::strstr(json, quoted);
  if (at == nullptr) return nullptr;
  at += std::strlen(quoted);
  while (*at == ' ') ++at;
  if (*at != ':') return nullptr;
  ++at;
  while (*at == ' ') ++at;
  return at;
}

}  // namespace

PiBattery parsePiBattery(const char* json) {
  PiBattery battery;
  if (json == nullptr) return battery;
  const char* object = valueOf(json, "pi_battery");
  if (object == nullptr || *object != '{') return battery;  // absent or null

  const char* percent = valueOf(object, "percent");
  const char* external = valueOf(object, "external_power");
  if (percent == nullptr || external == nullptr) return battery;

  char* end = nullptr;
  const long value = std::strtol(percent, &end, 10);
  if (end == percent || value < 0 || value > 100) return battery;

  battery.percent = static_cast<int>(value);
  battery.external_power = std::strncmp(external, "true", 4) == 0;
  battery.known = true;
  return battery;
}
```

Add `#include <cstdio>` for `snprintf`.

- [ ] **Step 4: Run all native tests to verify they pass**

Run: `pio test -d firmware/sticks3 -e native`
Expected: every suite passes, including 5 new cases in `test_status_fields`.

- [ ] **Step 5: Commit**

```bash
git add firmware/sticks3/include/status_fields.h firmware/sticks3/src/status_fields.cpp firmware/sticks3/test/test_status_fields/test_main.cpp firmware/sticks3/platformio.ini
git commit -m "Parse the Pi battery fields from the status payload"
```

---

### Task 6: Second badge on the display and the wiring in `main.cpp`

**Files:**
- Modify: `firmware/sticks3/include/display.h` (public API and members)
- Modify: `firmware/sticks3/src/display.cpp` (`drawColourBars`, `drawBatteryBadge`, `render`)
- Modify: `firmware/sticks3/src/main.cpp` (globals, the `WorkKind::Status` branch, `pollBattery` neighbour)
- Modify: `firmware/sticks3/README.md` (battery indicator section)

**Interfaces:**
- Consumes: `parsePiBattery` from Task 5; `BatteryMonitor`, `ChargeState` from `battery_status.h`; `StickDisplay::setBatteryLabel` from the base branch.
- Produces: `StickDisplay::setPiBatteryLabel(const char* label, bool low)`; constant `kPiBadgeWidth = 56`.

Layout: the Stick badge stays bottom-right (40 px). The Pi badge goes bottom-left, 56 px wide, text `Pi 87%+`. The READY caption is centred in the 144 px between them; at font size 1 it is 180 px wide, so shorten it to `READY • press button` (120 px). No native test covers drawing; the build and a look at the screen are the verification.

- [ ] **Step 1: Extend `display.h`**

Add next to `kBatteryBadgeWidth`:

```cpp
  // Bottom-left badge for the Pi's UPS battery ("Pi 87%+"); the READY caption
  // is centred in the space between the two badges.
  static constexpr int16_t kPiBadgeWidth = 56;
```

Add after `setBatteryLabel`:

```cpp
  // Pi battery text for the bottom-left badge; "Pi --%" when the Pi has no UPS.
  void setPiBatteryLabel(const char* label, bool low);
```

Add members after `battery_low_`:

```cpp
  char pi_battery_label_[12] = "";
  bool pi_battery_low_ = false;
```

- [ ] **Step 2: Extend `display.cpp`**

In `drawColourBars()`, replace the caption line with:

```cpp
  // Centred between the Pi badge (left) and the Stick badge (right).
  const int16_t caption_x = kPiBadgeWidth + (width_ - kPiBadgeWidth - kBatteryBadgeWidth) / 2;
  M5.Display.drawString("READY  \xE2\x80\xA2  press button", caption_x, height_ - 12);
```

(The `\xE2\x80\xA2` is the same bullet the caption already uses, written as UTF-8 bytes so the source stays ASCII.)

Add after `setBatteryLabel`:

```cpp
void StickDisplay::setPiBatteryLabel(const char* label, bool low) {
  std::strncpy(pi_battery_label_, label == nullptr ? "" : label, sizeof(pi_battery_label_) - 1);
  pi_battery_label_[sizeof(pi_battery_label_) - 1] = '\0';
  pi_battery_low_ = low;
  drawBatteryBadge();
}
```

Replace `drawBatteryBadge()` so it paints both corners:

```cpp
void StickDisplay::drawBatteryBadge() {
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(middle_center);
  const int16_t y = height_ - kBatteryBadgeHeight;
  if (battery_label_[0] != '\0') {
    const int16_t x = width_ - kBatteryBadgeWidth;
    M5.Display.fillRect(x, y, kBatteryBadgeWidth, kBatteryBadgeHeight, TFT_BLACK);
    M5.Display.setTextColor(battery_low_ ? TFT_RED : TFT_WHITE, TFT_BLACK);
    M5.Display.drawString(battery_label_, x + kBatteryBadgeWidth / 2, y + kBatteryBadgeHeight / 2);
  }
  if (pi_battery_label_[0] != '\0') {
    M5.Display.fillRect(0, y, kPiBadgeWidth, kBatteryBadgeHeight, TFT_BLACK);
    M5.Display.setTextColor(pi_battery_low_ ? TFT_RED : TFT_WHITE, TFT_BLACK);
    M5.Display.drawString(pi_battery_label_, kPiBadgeWidth / 2, y + kBatteryBadgeHeight / 2);
  }
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
}
```

`render()` already calls `drawBatteryBadge()` after every full redraw; nothing to change there.

- [ ] **Step 3: Wire it in `main.cpp`**

Add `#include "status_fields.h"` and a second monitor next to `BatteryMonitor battery;`:

```cpp
BatteryMonitor pi_battery;   // fed from /v1/status, not from the Stick's PM1
```

In `processWork`, inside the `WorkKind::Status` branch, after the `STICK_LOG("status: ...")` block and before `lockClient()`, add:

```cpp
    if (status == HTTP_CODE_OK) {
      const PiBattery pi = parsePiBattery(payload.c_str());
      const ChargeState charge = pi.known
          ? (pi.external_power ? ChargeState::Charging : ChargeState::Discharging)
          : ChargeState::Unknown;
      static bool pi_seen_once = false;
      // BatteryMonitor smooths and debounces; the Pi already averages, but the
      // deadband still stops a one-point wobble from repainting the badge.
      if (pi_battery.update(pi.known ? pi.percent : -1, charge, millis()) || !pi_seen_once) {
        pi_seen_once = true;
        char label[16];
        snprintf(label, sizeof(label), "Pi %s", pi_battery.label());
        lockClient();
        display.setPiBatteryLabel(label, pi_battery.low());
        unlockClient();
        STICK_LOG("pi battery %s (known=%d, %s)", pi_battery.label(), pi.known,
                  pi.external_power ? "external power" : "on battery");
      }
    }
```

Note the lock: `display` is otherwise only touched from the UI task under `capture_mutex`; the status branch runs on the network task, so it takes the same mutex for the badge repaint.

- [ ] **Step 4: Build, flash, verify**

Run: `pio test -d firmware/sticks3 -e native && pio run -d firmware/sticks3 -e sticks3 -t upload && pio device monitor -d firmware/sticks3 -b 115200`
Expected on the monitor within 2 s of READY: `pi battery 87%+ (known=1, external power)` with the Pi on its charger, and the bottom-left badge reads `Pi 87%+`. Pull the Pi's charger: within about 20 s the log shows `on battery` and the badge loses its `+`. Stop the Pi service, or run it without `--ups`: the badge reads `Pi --%`.

- [ ] **Step 5: Document and commit**

In `firmware/sticks3/README.md`, in the "Battery indicator" section, add a paragraph: the bottom-left badge shows the Pi's UPS battery as published by `GET /v1/status`, `Pi 87%+` with external power, `Pi --%` when the Pi has no UPS or the value is more than a minute old, red at 15% or below on battery. Then:

```bash
git add firmware/sticks3/include/display.h firmware/sticks3/src/display.cpp firmware/sticks3/src/main.cpp firmware/sticks3/README.md
git commit -m "Show the Pi's UPS battery in a second badge on the Stick"
```

---

### Task 7: Deploy on the Pi and update the guides

**Files:**
- Modify: `docs/setup.md` (section 4.4 unit explanation; new subsection 4.7 "UPS (optional)")
- Modify: `docs/sticks3-remote.md` (the `/v1/status` verification line)
- Modify: `todo.md` (section 3 and 4 items)

**Interfaces:**
- Consumes: everything above, merged and pulled onto the Pi.

- [ ] **Step 1: Deploy**

On the Pi, after `git pull` and `.venv/bin/python -m pip install -e .`:

```sh
sudo sed -i 's#\(--artifacts [^ ]*\)#\1 --ups x728#' /etc/systemd/system/parr-capture.service
grep ExecStart /etc/systemd/system/parr-capture.service
sudo systemctl daemon-reload && sudo systemctl restart parr-capture.service
sleep 25 && journalctl -u parr-capture.service -n 5 --no-pager
curl -s -H "Authorization: Bearer $(sudo grep -oP '(?<=PARR_REMOTE_TOKEN=).*' /etc/parr-capture.env)" http://10.42.0.1:8765/v1/status; echo
```

Expected: the journal shows `Reading the x728 UPS every 10 s.` and the status JSON contains `"pi_battery":{"percent":..,"voltage_mv":..,"external_power":true}`.

- [ ] **Step 2: Update the guides**

`docs/setup.md`: in 4.4, add `--ups x728` to the explained command line with one sentence: it reads the Geekworm fuel gauge for the Stick's Pi-battery badge and is dropped on a Pi without the shield. Add subsection "4.7 UPS (optional)" pointing to `docs/x728-ups.md` for the hardware and Geekworm services, and stating that `--ups x728` is the only project-side switch. `docs/sticks3-remote.md`, section 5 "Verify": extend the expected status line with `"pi_battery"` present when the UPS is configured. `todo.md`: check the section 3 RTC item (solved by the DS1307 overlay), check the section 3 "Shutdown from the Stick / include Pi battery level in /v1/status" item, and under section 4 record the X728 as the chosen UPS with the note that Geekworm requires unprotected cells.

- [ ] **Step 3: Commit**

```bash
git add docs/setup.md docs/sticks3-remote.md todo.md
git commit -m "Document the UPS battery badge and the X728 deployment"
```

---

## Out of scope, noted for later

- Recording `pi_battery` in each `captures.jsonl` record, for battery-per-shot analysis.
- Moving the low-battery shutdown decision from Geekworm's sample script into `parr-capture`, so there is one owner of the gauge and the Stick can show "Pi shutting down".
- A `POST /v1/system/shutdown` triggered from the Stick, which would pulse BCM 26 through `xSoft.sh`.

## Self-review

- Spec coverage: gauge decoding (T1), poller (T2), API (T3), CLI and service (T4), parser (T5), badge and wiring (T6), deployment and docs (T7). The `docs/x728-ups.md` prerequisite (I2C enabled) is stated up front.
- Placeholders: none; every code step has its code.
- Types: `PowerStatus(percent, voltage_mv, external_power)` is used identically in T1, T2, T3 and T4; `PowerMonitor.snapshot` is the callable passed as `power=` in T4 and consumed in T3; `PiBattery.known/percent/external_power` from T5 are the fields read in T6; `setPiBatteryLabel(label, low)` declared and used in T6.
