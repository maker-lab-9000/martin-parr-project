#include "capture_client.h"

#include <cstdio>
#include <cstring>

CaptureClient::CaptureClient() = default;

const char* clientStateName(ClientState state) {
  switch (state) {
    case ClientState::Connecting: return "CONNECTING";
    case ClientState::Ready: return "READY";
    case ClientState::Requesting: return "REQUESTING";
    case ClientState::Processing: return "PROCESSING";
    case ClientState::Downloading: return "DOWNLOADING";
    case ClientState::Photo: return "PHOTO";
    case ClientState::Error: return "ERROR";
  }
  return "UNKNOWN";
}

void CaptureClient::setWifiConnected(bool connected, uint32_t now_ms) {
  wifi_connected_ = connected;
  if (!connected) {
    api_ready_ = false;
    state_ = !active_request_ && has_photo_ ? ClientState::Photo : ClientState::Connecting;
    connect_in_flight_ = false;
    next_connect_at_ = now_ms + reconnect_backoff_ms_;
    return;
  }

  reconnect_backoff_ms_ = 1000;
  api_ready_ = false;
  server_has_active_job_ = false;
  status_in_flight_ = false;
  next_status_at_ = now_ms;
  // Wi-Fi association alone is not API readiness. An authenticated status
  // reply controls every transition into Ready.
  state_ = !active_request_ && has_photo_ ? ClientState::Photo : ClientState::Connecting;
}

bool CaptureClient::debouncedPress(bool pressed, uint32_t now_ms) {
  if (pressed != raw_button_) {
    raw_button_ = pressed;
    raw_changed_at_ = now_ms;
  }
  if (raw_button_ == stable_button_ || now_ms - raw_changed_at_ < kDebounceMs) {
    return false;
  }
  stable_button_ = raw_button_;
  return stable_button_;
}

bool CaptureClient::onButtonSample(bool pressed, uint32_t now_ms, const char* request_id) {
  if (!debouncedPress(pressed, now_ms) || active_request_ || !readyForCapture() ||
      (state_ != ClientState::Ready && state_ != ClientState::Photo) || request_id == nullptr) {
    return false;
  }
  if (std::strlen(request_id) != 36) {
    return false;
  }
  std::strncpy(request_id_, request_id, sizeof(request_id_) - 1);
  request_id_[36] = '\0';
  active_request_ = true;
  timed_out_ = false;
  photo_updated_ = false;
  shutter_pending_ = false;
  submit_in_flight_ = false;
  submitted_ = false;
  poll_in_flight_ = false;
  download_in_flight_ = false;
  retry_download_ = false;
  error_reason_ = ErrorReason::None;
  error_until_ = 0;
  started_at_ = now_ms;
  last_poll_at_ = now_ms;
  state_ = ClientState::Requesting;
  return true;
}

void CaptureClient::tick(uint32_t now_ms) {
  if (active_request_ && !timed_out_ && now_ms - started_at_ >= kJobTimeoutMs) {
    timed_out_ = true;
    error_reason_ = ErrorReason::Timeout;
    setError(now_ms);
  }
  if (!active_request_ && state_ == ClientState::Error && error_until_ != 0 && now_ms >= error_until_) {
    error_until_ = 0;
    error_reason_ = ErrorReason::None;
    state_ = has_photo_ ? ClientState::Photo
                       : (readyForCapture() ? ClientState::Ready : ClientState::Connecting);
  }
}

WorkItem CaptureClient::issue(WorkKind kind) {
  WorkItem item;
  item.kind = kind;
  std::strncpy(item.request_id, request_id_, sizeof(item.request_id) - 1);
  return item;
}

WorkItem CaptureClient::nextWork(uint32_t now_ms) {
  tick(now_ms);
  if (!wifi_connected_) {
    if (!connect_in_flight_ && now_ms >= next_connect_at_) {
      connect_in_flight_ = true;
      return issue(WorkKind::Connect);
    }
    return {};
  }
  if (!status_in_flight_ && now_ms >= next_status_at_) {
    status_in_flight_ = true;
    return issue(WorkKind::Status);
  }
  if (state_ == ClientState::Requesting && !submit_in_flight_) {
    submit_in_flight_ = true;
    return issue(WorkKind::Submit);
  }
  if (state_ == ClientState::Downloading && !download_in_flight_ && now_ms >= next_download_at_) {
    download_in_flight_ = true;
    return issue(WorkKind::Download);
  }
  if (state_ == ClientState::Error && retry_download_ && !download_in_flight_ && now_ms >= next_download_at_) {
    state_ = ClientState::Downloading;
    download_in_flight_ = true;
    return issue(WorkKind::Download);
  }
  if (active_request_ && !retry_download_ && !poll_in_flight_ && now_ms - last_poll_at_ >= kPollIntervalMs) {
    poll_in_flight_ = true;
    last_poll_at_ = now_ms;
    return issue(WorkKind::Poll);
  }
  return {};
}

void CaptureClient::submitStartFailed(uint32_t) {
  // HTTPClient::begin failed before any bytes reached the server. It is safe
  // to reissue the same idempotency key; do not switch to lookup yet.
  submit_in_flight_ = false;
  state_ = ClientState::Requesting;
}

void CaptureClient::completeSubmit(bool acknowledged, uint32_t now_ms) {
  // A missing response is ambiguous: POST is idempotent, so resolve it by
  // polling this same UUID instead of risking a second shutter action.
  submit_in_flight_ = false;
  submitted_ = true;
  if (acknowledged) shutter_pending_ = true;
  state_ = ClientState::Processing;
  last_poll_at_ = now_ms;
}

void CaptureClient::rejectSubmit(uint32_t now_ms) {
  submit_in_flight_ = false;
  active_request_ = false;
  retry_download_ = false;
  error_reason_ = ErrorReason::Rejected;
  error_until_ = now_ms + 2000;
  setError(now_ms);
}

void CaptureClient::completeServerStatus(bool ready, bool has_active_job, const char* instance_id, uint32_t now_ms) {
  status_in_flight_ = false;
  next_status_at_ = now_ms + kPollIntervalMs;
  if (!ready || instance_id == nullptr || std::strlen(instance_id) != 36) {
    api_ready_ = false;
    server_has_active_job_ = false;
    state_ = !active_request_ && has_photo_ ? ClientState::Photo : ClientState::Connecting;
    return;
  }
  api_ready_ = true;
  server_has_active_job_ = has_active_job;
  const bool changed = server_instance_id_[0] != '\0' && std::strcmp(server_instance_id_, instance_id) != 0;
  std::strncpy(server_instance_id_, instance_id, sizeof(server_instance_id_) - 1);
  server_instance_id_[36] = '\0';
  if (active_request_ && changed) {
    active_request_ = false;
    retry_download_ = false;
    poll_in_flight_ = false;
    download_in_flight_ = false;
    error_reason_ = ErrorReason::Interrupted;
    setError(now_ms);
    return;
  }
  if (active_request_) {
    if (error_reason_ == ErrorReason::Transport) error_reason_ = ErrorReason::None;
    state_ = timed_out_ ? ClientState::Error
                        : (!submitted_ ? ClientState::Requesting
                                       : (retry_download_ ? ClientState::Downloading : ClientState::Processing));
    return;
  }
  if (state_ == ClientState::Error && error_until_ != 0 && now_ms < error_until_) return;
  state_ = has_photo_ ? ClientState::Photo
                     : (has_active_job ? ClientState::Connecting : ClientState::Ready);
}

void CaptureClient::completeStatusTransportError(uint32_t now_ms) {
  status_in_flight_ = false;
  next_status_at_ = now_ms + kPollIntervalMs;
  // A failed authenticated status probe invalidates the cached readiness.
  // Treat the server as busy until a later successful response proves idle.
  api_ready_ = false;
  server_has_active_job_ = true;
  if (active_request_) {
    error_reason_ = ErrorReason::Transport;
    setError(now_ms);
  } else {
    state_ = has_photo_ ? ClientState::Photo : ClientState::Connecting;
  }
}

void CaptureClient::acceptStatus(JobStatus status, uint32_t now_ms) {
  poll_in_flight_ = false;
  last_poll_at_ = now_ms;
  switch (status) {
    case JobStatus::Pending:
    case JobStatus::Processing:
      if (error_reason_ == ErrorReason::Transport) error_reason_ = ErrorReason::None;
      if (!timed_out_) state_ = ClientState::Processing;
      break;
    case JobStatus::Complete:
      retry_download_ = true;
      next_download_at_ = now_ms;
      state_ = ClientState::Downloading;
      break;
    case JobStatus::Failed:
      active_request_ = false;
      retry_download_ = false;
      error_reason_ = ErrorReason::Rejected;
      error_until_ = now_ms + 2000;
      setError(now_ms);
      break;
    case JobStatus::Missing:
      // Unknown job IDs after a restart are intentionally not resubmitted.
      active_request_ = false;
      retry_download_ = false;
      error_reason_ = ErrorReason::Interrupted;
      setError(now_ms);
      break;
  }
}

void CaptureClient::completePollTransportError(uint32_t now_ms) {
  poll_in_flight_ = false;
  last_poll_at_ = now_ms;
  error_reason_ = ErrorReason::Transport;
  setError(now_ms);
}

void CaptureClient::completeDownload(bool decoded, uint32_t now_ms) {
  download_in_flight_ = false;
  if (decoded) {
    has_photo_ = true;
    photo_updated_ = true;
    active_request_ = false;
    retry_download_ = false;
    state_ = ClientState::Photo;
    return;
  }
  // Keep the last displayed photo and retry only retrieval, never submit.
  retry_download_ = true;
  next_download_at_ = now_ms + 1000;
  error_reason_ = ErrorReason::Image;
  setError(now_ms);
}

void CaptureClient::completeConnect(bool connected, uint32_t now_ms) {
  connect_in_flight_ = false;
  if (connected) {
    setWifiConnected(true, now_ms);
    return;
  }
  wifi_connected_ = false;
  next_connect_at_ = now_ms + reconnect_backoff_ms_;
  reconnect_backoff_ms_ = reconnect_backoff_ms_ >= 5000 ? 10000 : reconnect_backoff_ms_ * 2;
  api_ready_ = false;
  state_ = !active_request_ && has_photo_ ? ClientState::Photo : ClientState::Connecting;
}

bool CaptureClient::consumeShutterSound() {
  const bool value = shutter_pending_;
  shutter_pending_ = false;
  return value;
}

uint32_t CaptureClient::elapsedSeconds(uint32_t now_ms) const {
  return active_request_ ? (now_ms - started_at_) / 1000 : 0;
}

void CaptureClient::setError(uint32_t) { state_ = ClientState::Error; }

const char* CaptureClient::errorDetail() const {
  switch (error_reason_) {
    case ErrorReason::Interrupted: return "Capture interrupted; press again";
    case ErrorReason::Rejected: return "Capture request rejected";
    case ErrorReason::Timeout: return "Still looking up this request";
    case ErrorReason::Image: return "Retrying image";
    case ErrorReason::Transport: return "Retrying connection";
    case ErrorReason::None: return "Capture error";
  }
  return "Capture error";
}

void CaptureClient::makeUuid(const uint32_t random_words[4], char output[37]) {
  std::snprintf(output, 37, "%08lx-%04lx-4%03lx-%01lx%03lx-%04lx%08lx",
                static_cast<unsigned long>(random_words[0]),
                static_cast<unsigned long>((random_words[1] >> 16) & 0xffff),
                static_cast<unsigned long>(random_words[1] & 0x0fff),
                static_cast<unsigned long>(8 | ((random_words[2] >> 30) & 0x3)),
                static_cast<unsigned long>((random_words[2] >> 16) & 0x0fff),
                static_cast<unsigned long>(random_words[2] & 0xffff),
                static_cast<unsigned long>(random_words[3]));
}
