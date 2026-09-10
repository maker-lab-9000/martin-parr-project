"""The X728 fuel gauge and power-loss pin, decoded exactly as Geekworm's scripts do."""

import pytest

from parr.capture.power import (
    PowerError,
    PowerMonitor,
    PowerStatus,
    X728Ups,
    decode_word,
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
