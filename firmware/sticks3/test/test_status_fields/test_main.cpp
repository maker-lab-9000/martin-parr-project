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
