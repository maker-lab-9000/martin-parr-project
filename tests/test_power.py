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
