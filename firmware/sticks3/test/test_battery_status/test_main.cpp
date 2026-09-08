#ifdef PIO_UNIT_TESTING
#include <unity.h>
#else
#include <cassert>
#include <cstring>
#define TEST_ASSERT_TRUE(value) assert(value)
#define TEST_ASSERT_FALSE(value) assert(!(value))
#define TEST_ASSERT_EQUAL(expected, actual) assert((expected) == (actual))
#define TEST_ASSERT_EQUAL_STRING(expected, actual) assert(std::strcmp((expected), (actual)) == 0)
#endif

#include "battery_status.h"

namespace {

void test_initial_label_is_unknown_and_first_poll_is_due(void) {
  BatteryMonitor battery;

  TEST_ASSERT_EQUAL_STRING("--%", battery.label());
  TEST_ASSERT_EQUAL(-1, battery.level());
  TEST_ASSERT_TRUE(battery.pollDue(0));
  TEST_ASSERT_FALSE(battery.low());
}

void test_label_shows_percent_and_a_plus_while_charging(void) {
  BatteryMonitor battery;

  TEST_ASSERT_TRUE(battery.update(87, ChargeState::Discharging, 0));
  TEST_ASSERT_EQUAL_STRING("87%", battery.label());
  TEST_ASSERT_TRUE(battery.update(87, ChargeState::Charging, 10000));
  TEST_ASSERT_EQUAL_STRING("87%+", battery.label());
  // An unknown answer from the chip is no information: keep what is shown.
  TEST_ASSERT_FALSE(battery.update(87, ChargeState::Unknown, 20000));
  TEST_ASSERT_EQUAL_STRING("87%+", battery.label());
}

void test_external_power_presence_outranks_the_charger_status_pin(void) {
  // The StickS3 charger's status pin cycles on and off for ~20 s at a time
  // while plugged in, so the mark must come from "is external power present",
  // and fall back to the charger pin only when the PM1 cannot say.
  TEST_ASSERT_EQUAL(ChargeState::Charging, chargeStateFrom(true, true, ChargeState::Discharging));
  TEST_ASSERT_EQUAL(ChargeState::Discharging, chargeStateFrom(true, false, ChargeState::Charging));
  TEST_ASSERT_EQUAL(ChargeState::Charging, chargeStateFrom(false, false, ChargeState::Charging));
  TEST_ASSERT_EQUAL(ChargeState::Unknown, chargeStateFrom(false, false, ChargeState::Unknown));
}

void test_first_reading_with_unknown_charge_shows_plain_percent(void) {
  BatteryMonitor battery;

  TEST_ASSERT_TRUE(battery.update(87, ChargeState::Unknown, 0));
  TEST_ASSERT_EQUAL_STRING("87%", battery.label());
}

void test_plugging_in_shows_the_charging_mark_immediately(void) {
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  TEST_ASSERT_TRUE(battery.update(80, ChargeState::Charging, 10000));
  TEST_ASSERT_EQUAL_STRING("80%+", battery.label());
}

void test_one_discharging_reading_does_not_drop_the_charging_mark(void) {
  // Measured on the StickS3 with USB attached: the PM1 reported discharging
  // for a single 10 s poll and charging again on the next one. A lone reading
  // must not blink the mark.
  BatteryMonitor battery;
  battery.update(80, ChargeState::Charging, 0);

  TEST_ASSERT_FALSE(battery.update(78, ChargeState::Discharging, 10000));
  TEST_ASSERT_EQUAL_STRING("80%+", battery.label());
  TEST_ASSERT_FALSE(battery.update(80, ChargeState::Charging, 20000));
  TEST_ASSERT_EQUAL_STRING("80%+", battery.label());
}

void test_two_consecutive_discharging_readings_drop_the_charging_mark(void) {
  BatteryMonitor battery;
  battery.update(80, ChargeState::Charging, 0);

  TEST_ASSERT_FALSE(battery.update(80, ChargeState::Discharging, 10000));
  TEST_ASSERT_TRUE(battery.update(80, ChargeState::Discharging, 20000));
  TEST_ASSERT_EQUAL_STRING("80%", battery.label());
}

void test_level_is_clamped_to_percent_and_negative_means_unknown(void) {
  BatteryMonitor battery;

  battery.update(140, ChargeState::Discharging, 0);
  TEST_ASSERT_EQUAL_STRING("100%", battery.label());
  TEST_ASSERT_EQUAL(100, battery.level());
  battery.update(-1, ChargeState::Charging, 10000);
  TEST_ASSERT_EQUAL_STRING("--%", battery.label());
  TEST_ASSERT_EQUAL(-1, battery.level());
}

void test_update_reports_a_change_only_when_the_label_changes(void) {
  BatteryMonitor battery;

  TEST_ASSERT_TRUE(battery.update(50, ChargeState::Discharging, 0));
  TEST_ASSERT_FALSE(battery.update(50, ChargeState::Discharging, 10000));
  TEST_ASSERT_TRUE(battery.update(50, ChargeState::Charging, 20000));
  TEST_ASSERT_TRUE(battery.update(-1, ChargeState::Charging, 30000));
}

void test_small_wobbles_inside_the_deadband_do_not_move_the_label(void) {
  // The PM1 level is derived from voltage and wobbles by a point or two per
  // poll, which made the badge flicker every 10 s. Hold the shown level until
  // the smoothed reading has moved by at least kHysteresisPercent.
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  TEST_ASSERT_FALSE(battery.update(79, ChargeState::Discharging, 10000));
  TEST_ASSERT_FALSE(battery.update(78, ChargeState::Discharging, 20000));
  TEST_ASSERT_FALSE(battery.update(81, ChargeState::Discharging, 30000));
  TEST_ASSERT_EQUAL_STRING("80%", battery.label());
  TEST_ASSERT_EQUAL(80, battery.level());
}

void test_a_sustained_lower_reading_is_followed_within_ten_polls(void) {
  // Smoothing must not stop the badge from tracking a real change.
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  int changes = 0;
  for (int poll = 1; poll <= 10; ++poll) {
    if (battery.update(77, ChargeState::Discharging, poll * 10000u)) ++changes;
  }
  TEST_ASSERT_EQUAL(1, changes);
  TEST_ASSERT_EQUAL_STRING("77%", battery.label());
}

void test_readings_alternating_by_five_points_settle_instead_of_flickering(void) {
  // Measured on the StickS3: 81, 75, 80, 75, 80 ... as the Wi-Fi radio loads
  // the battery between polls. The badge must settle, not follow each swing.
  BatteryMonitor battery;
  battery.update(81, ChargeState::Charging, 0);

  int changes = 0;
  for (int poll = 1; poll <= 12; ++poll) {
    const int reading = (poll % 2) ? 75 : 80;
    if (battery.update(reading, ChargeState::Charging, poll * 10000u)) ++changes;
  }
  TEST_ASSERT_TRUE(changes <= 1);
  TEST_ASSERT_TRUE(battery.level() >= 76 && battery.level() <= 79);
}

void test_a_steady_drain_is_tracked_with_bounded_lag(void) {
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  for (int poll = 1; poll <= 10; ++poll) {
    battery.update(80 - poll, ChargeState::Discharging, poll * 10000u);  // ends at 70
  }
  TEST_ASSERT_TRUE(battery.level() <= 76);
  TEST_ASSERT_TRUE(battery.level() >= 70);
}

void test_charge_state_change_updates_the_label_even_inside_the_deadband(void) {
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  TEST_ASSERT_TRUE(battery.update(79, ChargeState::Charging, 10000));
  TEST_ASSERT_EQUAL_STRING("80%+", battery.label());
}

void test_unknown_reading_and_recovery_bypass_the_deadband(void) {
  BatteryMonitor battery;
  battery.update(80, ChargeState::Discharging, 0);

  TEST_ASSERT_TRUE(battery.update(-1, ChargeState::Discharging, 10000));
  TEST_ASSERT_EQUAL_STRING("--%", battery.label());
  TEST_ASSERT_TRUE(battery.update(79, ChargeState::Discharging, 20000));
  TEST_ASSERT_EQUAL_STRING("79%", battery.label());
}

void test_poll_is_due_on_the_interval_after_the_first_update(void) {
  BatteryMonitor battery;
  battery.update(50, ChargeState::Discharging, 1000);

  TEST_ASSERT_FALSE(battery.pollDue(1000 + BatteryMonitor::kPollIntervalMs - 1));
  TEST_ASSERT_TRUE(battery.pollDue(1000 + BatteryMonitor::kPollIntervalMs));
}

void test_low_battery_is_fifteen_percent_or_less_and_not_charging(void) {
  BatteryMonitor battery;

  battery.update(16, ChargeState::Discharging, 0);
  TEST_ASSERT_FALSE(battery.low());
  for (int poll = 1; poll <= 6; ++poll) {
    battery.update(10, ChargeState::Discharging, poll * 10000u);  // sustained, past the deadband
  }
  TEST_ASSERT_TRUE(battery.low());
  battery.update(10, ChargeState::Charging, 70000);
  TEST_ASSERT_FALSE(battery.low());
  battery.update(-1, ChargeState::Discharging, 80000);
  TEST_ASSERT_FALSE(battery.low());
}

void run_all(void) {
  UNITY_BEGIN();
  RUN_TEST(test_initial_label_is_unknown_and_first_poll_is_due);
  RUN_TEST(test_label_shows_percent_and_a_plus_while_charging);
  RUN_TEST(test_external_power_presence_outranks_the_charger_status_pin);
  RUN_TEST(test_first_reading_with_unknown_charge_shows_plain_percent);
  RUN_TEST(test_plugging_in_shows_the_charging_mark_immediately);
  RUN_TEST(test_one_discharging_reading_does_not_drop_the_charging_mark);
  RUN_TEST(test_two_consecutive_discharging_readings_drop_the_charging_mark);
  RUN_TEST(test_level_is_clamped_to_percent_and_negative_means_unknown);
  RUN_TEST(test_update_reports_a_change_only_when_the_label_changes);
  RUN_TEST(test_small_wobbles_inside_the_deadband_do_not_move_the_label);
  RUN_TEST(test_a_sustained_lower_reading_is_followed_within_ten_polls);
  RUN_TEST(test_readings_alternating_by_five_points_settle_instead_of_flickering);
  RUN_TEST(test_a_steady_drain_is_tracked_with_bounded_lag);
  RUN_TEST(test_charge_state_change_updates_the_label_even_inside_the_deadband);
  RUN_TEST(test_unknown_reading_and_recovery_bypass_the_deadband);
  RUN_TEST(test_poll_is_due_on_the_interval_after_the_first_update);
  RUN_TEST(test_low_battery_is_fifteen_percent_or_less_and_not_charging);
  UNITY_END();
}

}  // namespace

#ifdef PIO_UNIT_TESTING
int main(int, char**) {
  run_all();
  return 0;
}
#else
int main() {
  run_all();
  return 0;
}
#endif
