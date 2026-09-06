#pragma once

#include <cstdint>

enum class ClientState : uint8_t {
  Connecting,
  Ready,
  Requesting,
  Processing,
  Downloading,
  Photo,
  Error,
};

enum class JobStatus : uint8_t { Pending, Processing, Complete, Failed, Missing };
enum class WorkKind : uint8_t { None, Connect, Status, Submit, Poll, Download };
enum class ErrorReason : uint8_t { None, Transport, Timeout, Interrupted, Rejected, Image };

struct WorkItem {
  WorkKind kind = WorkKind::None;
  char request_id[37] = {};
};

// This class deliberately has no Arduino, Wi-Fi, HTTP, or display dependency.
// The worker owns transport; the UI consumes this state and completed JPEGs.
class CaptureClient {
 public:
  static constexpr uint32_t kDebounceMs = 30;
  static constexpr uint32_t kPollIntervalMs = 500;
  static constexpr uint32_t kJobTimeoutMs = 120000;

  CaptureClient();

  void setWifiConnected(bool connected, uint32_t now_ms);
  bool onButtonSample(bool pressed, uint32_t now_ms, const char* request_id);
  void tick(uint32_t now_ms);

  WorkItem nextWork(uint32_t now_ms);
  void submitStartFailed(uint32_t now_ms);
  void completeSubmit(bool acknowledged, uint32_t now_ms);
  void rejectSubmit(uint32_t now_ms);
  void completeServerStatus(bool ready, bool has_active_job, const char* instance_id, uint32_t now_ms);
  void completeStatusTransportError(uint32_t now_ms);
  void acceptStatus(JobStatus status, uint32_t now_ms);
  void completePollTransportError(uint32_t now_ms);
  void completeDownload(bool decoded, uint32_t now_ms);
  void completeConnect(bool connected, uint32_t now_ms);

  ClientState state() const { return state_; }
  const char* requestId() const { return request_id_; }
  bool hasActiveRequest() const { return active_request_; }
  bool readyForCapture() const { return wifi_connected_ && api_ready_ && !server_has_active_job_; }
  uint32_t elapsedSeconds(uint32_t now_ms) const;
  bool timedOut() const { return timed_out_; }
  bool photoWasUpdated() const { return photo_updated_; }
  const char* serverInstanceId() const { return server_instance_id_; }
  const char* errorDetail() const;
  bool consumeShutterSound();

  // Turns four independent random words into an RFC 4122 v4 UUID.
  static void makeUuid(const uint32_t random_words[4], char output[37]);

 private:
  bool debouncedPress(bool pressed, uint32_t now_ms);
  void setError(uint32_t now_ms);
  WorkItem issue(WorkKind kind);

  ClientState state_ = ClientState::Connecting;
  char request_id_[37] = {};
  bool wifi_connected_ = false;
  bool api_ready_ = false;
  bool server_has_active_job_ = false;
  bool active_request_ = false;
  bool timed_out_ = false;
  bool photo_updated_ = false;
  bool has_photo_ = false;
  bool shutter_pending_ = false;
  bool raw_button_ = false;
  bool stable_button_ = false;
  bool submit_in_flight_ = false;
  bool submitted_ = false;
  bool status_in_flight_ = false;
  bool poll_in_flight_ = false;
  bool download_in_flight_ = false;
  bool connect_in_flight_ = false;
  bool retry_download_ = false;
  uint32_t raw_changed_at_ = 0;
  uint32_t started_at_ = 0;
  uint32_t last_poll_at_ = 0;
  uint32_t next_status_at_ = 0;
  uint32_t next_connect_at_ = 0;
  uint32_t next_download_at_ = 0;
  uint32_t reconnect_backoff_ms_ = 1000;
  uint32_t error_until_ = 0;
  ErrorReason error_reason_ = ErrorReason::None;
  char server_instance_id_[37] = {};
};
