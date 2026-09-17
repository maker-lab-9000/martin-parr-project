"""The X728 fuel gauge and power-loss pin, decoded exactly as Geekworm's scripts do."""

import pytest

from pifilm.capture.power import (
    PowerError,
    PowerMonitor,
    PowerStatus,
    X728Ups,
    build_ups,
    decode_word,
    format_status,
    main,
)


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


def test_poll_once_survives_repeated_failures_and_warns_once_then_recovers(capsys):
    clock = FakeClock()
    reading = PowerStatus(percent=87, voltage_mv=4000, external_power=True)
    provider = ScriptedProvider([RuntimeError("boom"), RuntimeError("boom"), reading])
    monitor = PowerMonitor(provider, clock=clock)

    monitor.poll_once()
    assert monitor.last_error == "boom"
    assert monitor.snapshot() is None
    assert capsys.readouterr().err == "warning: UPS read failed: boom\n"

    monitor.poll_once()  # still failing: no repeat warning
    assert monitor.last_error == "boom"
    assert capsys.readouterr().err == ""

    monitor.poll_once()
    assert monitor.last_error is None
    assert monitor.snapshot() == reading
    assert capsys.readouterr().err == "UPS read recovered\n"


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
    readings = [
        PowerStatus(percent=p, voltage_mv=4000, external_power=True) for p in (90, 89, 88)
    ]
    monitor = PowerMonitor(
        ScriptedProvider(readings), interval_s=10.0, clock=clock, sleep=sleeps.append
    )
    # Drive the loop body directly instead of a real thread: deterministic and fast.
    for _ in range(3):
        monitor._poll_and_wait()
    monitor.close()

    assert monitor.snapshot().percent == 88
    assert sleeps == [10.0, 10.0, 10.0]


def test_start_runs_a_daemon_thread_that_polls_and_close_stops_it_promptly():
    import time

    reading = PowerStatus(percent=87, voltage_mv=4000, external_power=True)

    class Endless:
        def read(self):
            return reading

    monitor = PowerMonitor(Endless(), interval_s=10.0)  # real clock, real (interruptible) sleep
    monitor.start()
    deadline = time.monotonic() + 2.0
    while monitor.snapshot() is None and time.monotonic() < deadline:
        time.sleep(0.005)
    assert monitor.snapshot() == reading
    assert monitor._thread is not None and monitor._thread.daemon

    started_close = time.monotonic()
    monitor.close()
    assert not monitor._thread.is_alive()
    # The 10 s interval must not delay shutdown: close() interrupts the wait.
    assert time.monotonic() - started_close < 2.0


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


def test_build_ups_x728_explains_missing_libraries_without_the_i2c_remedy():
    def open_bus(number):
        raise ModuleNotFoundError("No module named 'smbus2'", name="smbus2")

    with pytest.raises(PowerError, match="python3-smbus2") as info:
        build_ups("x728", open_bus=open_bus, open_pin=lambda n: (lambda: False))
    assert "raspi-config" not in str(info.value)


def test_build_ups_x728_explains_a_pin_claim_failure():
    def open_pin(number):
        raise RuntimeError("GPIO busy")

    with pytest.raises(PowerError, match="BCM 6") as info:
        build_ups("x728", open_bus=lambda n: FakeBus({}), open_pin=open_pin)
    assert "I2C" not in str(info.value)


def test_build_ups_x728_explains_missing_gpiozero_for_the_pin():
    def open_pin(number):
        raise ModuleNotFoundError("No module named 'gpiozero'", name="gpiozero")

    with pytest.raises(PowerError, match="python3-gpiozero") as info:
        build_ups("x728", open_bus=lambda n: FakeBus({}), open_pin=open_pin)
    assert "raspi-config" not in str(info.value)


def test_build_ups_rejects_unknown_names():
    with pytest.raises(PowerError, match="x728"):
        build_ups("apc")


# --- pifilm-battery CLI -----------------------------------------------------


def _battery_build(words=None, pld_high=False):
    """A build_ups replacement that wires the CLI to a FakeBus, no hardware."""
    gauge = words or {0x02: 0x00C8, 0x04: 0x8057}  # 4.00 V, 87 %

    def build(name):
        return PowerMonitor(X728Ups(FakeBus(gauge), pld_is_high=lambda: pld_high))

    return build


def test_format_status_reads_as_a_human_line_on_battery():
    status = PowerStatus(percent=64, voltage_mv=3850, external_power=False)
    assert format_status(status) == "Battery: 64%  3.85 V  on battery"


def test_format_status_names_external_power():
    line = format_status(PowerStatus(percent=87, voltage_mv=4000, external_power=True))
    assert "87%" in line
    assert "on external power" in line


def test_main_prints_the_battery_line(capsys):
    rc = main([], build=_battery_build(pld_high=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "87%" in out
    assert "4.00 V" in out
    assert "on battery" in out


def test_main_reports_no_ups_configured(capsys):
    rc = main(["--ups", "none"], build=build_ups)
    assert rc == 2
    assert "no UPS" in capsys.readouterr().err


def test_main_reports_a_read_failure_without_crashing(capsys):
    class BrokenBus:
        def read_word_data(self, address, register):
            raise OSError(121, "Remote I/O error")

    def build(name):
        return PowerMonitor(X728Ups(BrokenBus(), pld_is_high=lambda: False))

    rc = main([], build=build)
    assert rc == 1
    assert "could not read" in capsys.readouterr().err.lower()
