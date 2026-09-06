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

#include "capture_client.h"

namespace {

void settle_button(CaptureClient& client, uint32_t at_ms, const char* id) {
  TEST_ASSERT_FALSE(client.onButtonSample(true, at_ms, id));
  const bool accepted = client.onButtonSample(true, at_ms + 30, id);
  TEST_ASSERT_TRUE(accepted);
}

void make_ready(CaptureClient& client, uint32_t at_ms = 0, const char* instance = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") {
  client.setWifiConnected(true, at_ms);
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(at_ms).kind);
  client.completeServerStatus(true, false, instance, at_ms + 1);
  TEST_ASSERT_EQUAL(ClientState::Ready, client.state());
}

void test_ready_requires_authenticated_server_status_without_active_job(void) {
  CaptureClient client;
  client.setWifiConnected(true, 0);

  TEST_ASSERT_EQUAL(ClientState::Connecting, client.state());
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(0).kind);
  client.completeServerStatus(true, true, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 1);
  TEST_ASSERT_EQUAL(ClientState::Connecting, client.state());
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 2);
  TEST_ASSERT_EQUAL(ClientState::Ready, client.state());
}

void test_press_starts_one_request_and_one_shutter_sound(void) {
  CaptureClient client;
  make_ready(client);

  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  TEST_ASSERT_EQUAL(ClientState::Requesting, client.state());
  TEST_ASSERT_FALSE(client.consumeShutterSound());
  client.completeSubmit(true, 50);
  TEST_ASSERT_TRUE(client.consumeShutterSound());
  TEST_ASSERT_FALSE(client.consumeShutterSound());
  TEST_ASSERT_FALSE(client.onButtonSample(true, 100, "22222222-2222-4222-8222-222222222222"));
  TEST_ASSERT_EQUAL_STRING("11111111-1111-4111-8111-111111111111", client.requestId());
}

void test_lost_submission_acknowledgement_is_resolved_by_polling_same_id(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  TEST_ASSERT_FALSE(client.consumeShutterSound());

  client.completeSubmit(false, 50);  // TCP response was lost.

  TEST_ASSERT_EQUAL(ClientState::Processing, client.state());
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(550).kind);
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 550);
  const WorkItem work = client.nextWork(550);
  TEST_ASSERT_EQUAL(WorkKind::Poll, work.kind);
  TEST_ASSERT_EQUAL_STRING("11111111-1111-4111-8111-111111111111", work.request_id);
  TEST_ASSERT_FALSE(client.consumeShutterSound());
}

void test_restart_or_missing_job_interrupts_and_requires_a_fresh_press(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);
  client.acceptStatus(JobStatus::Missing, 550);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
  TEST_ASSERT_FALSE(client.hasActiveRequest());
  TEST_ASSERT_EQUAL_STRING("11111111-1111-4111-8111-111111111111", client.requestId());
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(1050).kind);
}

void test_changed_server_instance_interrupts_active_job(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);

  client.completeServerStatus(true, false, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 550);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
  TEST_ASSERT_FALSE(client.hasActiveRequest());
  TEST_ASSERT_EQUAL_STRING("Capture interrupted; press again", client.errorDetail());
}

void test_failed_or_truncated_jpeg_never_replaces_photo(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);
  client.acceptStatus(JobStatus::Complete, 550);
  TEST_ASSERT_EQUAL(ClientState::Downloading, client.state());

  client.completeDownload(false, 600);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
  TEST_ASSERT_TRUE(client.hasActiveRequest());
  TEST_ASSERT_FALSE(client.photoWasUpdated());
}

void test_unresolved_job_times_out_but_keeps_polling_its_id(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);

  client.tick(120040);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
  TEST_ASSERT_TRUE(client.timedOut());
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(120510).kind);
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 120510);
  TEST_ASSERT_EQUAL(WorkKind::Poll, client.nextWork(120510).kind);
}

void test_elapsed_indicator_starts_at_deliberate_press(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 1000, "11111111-1111-4111-8111-111111111111");

  TEST_ASSERT_EQUAL(2u, client.elapsedSeconds(3030));
}

void test_timeout_message_survives_wifi_reconnect(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);
  client.tick(120040);

  client.setWifiConnected(false, 120050);
  client.setWifiConnected(true, 121000);
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 121001);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
}

void test_wifi_reconnect_backoff_starts_at_one_second_and_never_exceeds_ten(void) {
  CaptureClient client;
  client.setWifiConnected(false, 0);

  TEST_ASSERT_EQUAL(WorkKind::None, client.nextWork(999).kind);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(1000).kind);
  client.completeConnect(false, 1000);
  TEST_ASSERT_EQUAL(WorkKind::None, client.nextWork(1999).kind);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(2000).kind);
  client.completeConnect(false, 2000);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(4000).kind);
  client.completeConnect(false, 4000);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(8000).kind);
  client.completeConnect(false, 8000);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(16000).kind);
  client.completeConnect(false, 16000);
  TEST_ASSERT_EQUAL(WorkKind::None, client.nextWork(25999).kind);
  TEST_ASSERT_EQUAL(WorkKind::Connect, client.nextWork(26000).kind);
}

void test_reconnect_before_submission_preserves_the_submit_work(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");

  client.setWifiConnected(false, 45);
  client.setWifiConnected(true, 1000);
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(1000).kind);
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 1001);

  TEST_ASSERT_EQUAL(ClientState::Requesting, client.state());
  const WorkItem work = client.nextWork(1000);
  TEST_ASSERT_EQUAL(WorkKind::Submit, work.kind);
  TEST_ASSERT_EQUAL_STRING("11111111-1111-4111-8111-111111111111", work.request_id);
}

void test_known_submission_rejection_releases_button_for_a_later_press(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.rejectSubmit(50);

  TEST_ASSERT_EQUAL(ClientState::Error, client.state());
  TEST_ASSERT_FALSE(client.hasActiveRequest());
  TEST_ASSERT_EQUAL_STRING("Capture request rejected", client.errorDetail());
  client.tick(2050);
  TEST_ASSERT_EQUAL(ClientState::Ready, client.state());
  client.onButtonSample(false, 60, "ignored");
  client.onButtonSample(false, 90, "ignored");
  TEST_ASSERT_FALSE(client.onButtonSample(true, 100, "22222222-2222-4222-8222-222222222222"));
  TEST_ASSERT_TRUE(client.onButtonSample(true, 130, "22222222-2222-4222-8222-222222222222"));
  TEST_ASSERT_EQUAL_STRING("22222222-2222-4222-8222-222222222222", client.requestId());
}

void test_rejection_expiry_does_not_claim_ready_while_server_has_an_active_job(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.rejectSubmit(50);
  client.completeServerStatus(true, true, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 550);

  client.tick(2050);

  TEST_ASSERT_EQUAL(ClientState::Connecting, client.state());
}

void test_successful_status_clears_active_transport_error(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  client.completeSubmit(true, 50);
  client.completePollTransportError(550);
  TEST_ASSERT_EQUAL(ClientState::Error, client.state());

  client.completeServerStatus(true, true, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 600);

  TEST_ASSERT_EQUAL(ClientState::Processing, client.state());
  TEST_ASSERT_EQUAL_STRING("Capture error", client.errorDetail());
}

void test_submit_start_failure_retries_the_same_uuid_without_polling(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");
  TEST_ASSERT_EQUAL(WorkKind::Submit, client.nextWork(40).kind);

  client.submitStartFailed(50);

  TEST_ASSERT_EQUAL(ClientState::Requesting, client.state());
  const WorkItem retry = client.nextWork(50);
  TEST_ASSERT_EQUAL(WorkKind::Submit, retry.kind);
  TEST_ASSERT_EQUAL_STRING("11111111-1111-4111-8111-111111111111", retry.request_id);
}

void test_only_acknowledged_post_queues_the_one_shutter_tone(void) {
  CaptureClient client;
  make_ready(client);
  settle_button(client, 10, "11111111-1111-4111-8111-111111111111");

  client.completeSubmit(false, 50);

  TEST_ASSERT_FALSE(client.consumeShutterSound());
  TEST_ASSERT_EQUAL(WorkKind::Status, client.nextWork(550).kind);
  client.completeServerStatus(true, false, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 550);
  TEST_ASSERT_EQUAL(WorkKind::Poll, client.nextWork(550).kind);
}

void test_uuid_is_rfc4122_version_four_shape(void) {
  const uint32_t random_words[] = {0x01234567, 0x89abcdef, 0x10203040, 0x50607080};
  char id[37] = {};
  CaptureClient::makeUuid(random_words, id);

  TEST_ASSERT_EQUAL_STRING("01234567-89ab-4def-8020-304050607080", id);
}

}  // namespace

#ifdef PIO_UNIT_TESTING
void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_ready_requires_authenticated_server_status_without_active_job);
  RUN_TEST(test_press_starts_one_request_and_one_shutter_sound);
  RUN_TEST(test_lost_submission_acknowledgement_is_resolved_by_polling_same_id);
  RUN_TEST(test_restart_or_missing_job_interrupts_and_requires_a_fresh_press);
  RUN_TEST(test_changed_server_instance_interrupts_active_job);
  RUN_TEST(test_failed_or_truncated_jpeg_never_replaces_photo);
  RUN_TEST(test_unresolved_job_times_out_but_keeps_polling_its_id);
  RUN_TEST(test_elapsed_indicator_starts_at_deliberate_press);
  RUN_TEST(test_timeout_message_survives_wifi_reconnect);
  RUN_TEST(test_wifi_reconnect_backoff_starts_at_one_second_and_never_exceeds_ten);
  RUN_TEST(test_reconnect_before_submission_preserves_the_submit_work);
  RUN_TEST(test_known_submission_rejection_releases_button_for_a_later_press);
  RUN_TEST(test_rejection_expiry_does_not_claim_ready_while_server_has_an_active_job);
  RUN_TEST(test_successful_status_clears_active_transport_error);
  RUN_TEST(test_submit_start_failure_retries_the_same_uuid_without_polling);
  RUN_TEST(test_only_acknowledged_post_queues_the_one_shutter_tone);
  RUN_TEST(test_uuid_is_rfc4122_version_four_shape);
  UNITY_END();
}

int main(int, char**) {
  setup();
  return 0;
}
#else
int main() {
  test_ready_requires_authenticated_server_status_without_active_job();
  test_press_starts_one_request_and_one_shutter_sound();
  test_lost_submission_acknowledgement_is_resolved_by_polling_same_id();
  test_restart_or_missing_job_interrupts_and_requires_a_fresh_press();
  test_changed_server_instance_interrupts_active_job();
  test_failed_or_truncated_jpeg_never_replaces_photo();
  test_unresolved_job_times_out_but_keeps_polling_its_id();
  test_elapsed_indicator_starts_at_deliberate_press();
  test_timeout_message_survives_wifi_reconnect();
  test_wifi_reconnect_backoff_starts_at_one_second_and_never_exceeds_ten();
  test_reconnect_before_submission_preserves_the_submit_work();
  test_known_submission_rejection_releases_button_for_a_later_press();
  test_rejection_expiry_does_not_claim_ready_while_server_has_an_active_job();
  test_successful_status_clears_active_transport_error();
  test_submit_start_failure_retries_the_same_uuid_without_polling();
  test_only_acknowledged_post_queues_the_one_shutter_tone();
  test_uuid_is_rfc4122_version_four_shape();
  return 0;
}
#endif
