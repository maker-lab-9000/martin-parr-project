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
  // Unknown charge state is shown as plain percent rather than guessed.
  TEST_ASSERT_TRUE(battery.update(87, ChargeState::Unknown, 20000));
  TEST_ASSERT_EQUAL_STRING("87%", battery.label());
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
  TEST_ASSERT_TRUE(battery.update(49, ChargeState::Discharging, 20000));
  TEST_ASSERT_TRUE(battery.update(49, ChargeState::Charging, 30000));
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
  battery.update(15, ChargeState::Discharging, 10000);
  TEST_ASSERT_TRUE(battery.low());
  battery.update(15, ChargeState::Charging, 20000);
  TEST_ASSERT_FALSE(battery.low());
  battery.update(-1, ChargeState::Discharging, 30000);
  TEST_ASSERT_FALSE(battery.low());
}

void run_all(void) {
  UNITY_BEGIN();
  RUN_TEST(test_initial_label_is_unknown_and_first_poll_is_due);
  RUN_TEST(test_label_shows_percent_and_a_plus_while_charging);
  RUN_TEST(test_level_is_clamped_to_percent_and_negative_means_unknown);
  RUN_TEST(test_update_reports_a_change_only_when_the_label_changes);
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
