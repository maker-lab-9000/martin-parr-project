#include "capture_client.h"

#include <cstdio>
#include <cstring>

CaptureClient::CaptureClient() = default;

void CaptureClient::setWifiConnected(bool connected, uint32_t now_ms) {
  wifi_connected_ = connected;
  if (!connected) {
    state_ = ClientState::Connecting;
    connect_in_flight_ = false;
    next_connect_at_ = now_ms + reconnect_backoff_ms_;
    return;
  }

  reconnect_backoff_ms_ = 1000;
  if (active_request_) {
    state_ = timed_out_ ? ClientState::Error
                        : (!submitted_ ? ClientState::Requesting
                                       : (retry_download_ ? ClientState::Downloading : ClientState::Processing));
  } else {
    state_ = ClientState::Ready;
  }
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
  if (!debouncedPress(pressed, now_ms) || active_request_ || !wifi_connected_ || request_id == nullptr) {
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
  shutter_pending_ = true;
  submit_in_flight_ = false;
  submitted_ = false;
  poll_in_flight_ = false;
  download_in_flight_ = false;
  retry_download_ = false;
  started_at_ = now_ms;
  last_poll_at_ = now_ms;
  state_ = ClientState::Requesting;
  return true;
}

void CaptureClient::tick(uint32_t now_ms) {
  if (active_request_ && !timed_out_ && now_ms - started_at_ >= kJobTimeoutMs) {
    timed_out_ = true;
    setError(now_ms);
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
  (void)acknowledged;
  // A missing response is ambiguous: POST is idempotent, so resolve it by
  // polling this same UUID instead of risking a second shutter action.
  submit_in_flight_ = false;
  submitted_ = true;
  state_ = ClientState::Processing;
  last_poll_at_ = now_ms;
}

void CaptureClient::rejectSubmit(uint32_t now_ms) {
  submit_in_flight_ = false;
  active_request_ = false;
  retry_download_ = false;
  setError(now_ms);
}

void CaptureClient::acceptStatus(JobStatus status, uint32_t now_ms) {
  poll_in_flight_ = false;
  last_poll_at_ = now_ms;
  switch (status) {
    case JobStatus::Pending:
    case JobStatus::Processing:
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
      setError(now_ms);
      break;
    case JobStatus::Missing:
      // A server restart can lose its in-memory registry. Preserve the ID and
      // continue bounded polling rather than silently creating another job.
      setError(now_ms);
      break;
  }
}

void CaptureClient::completePollTransportError(uint32_t now_ms) {
  poll_in_flight_ = false;
  last_poll_at_ = now_ms;
  setError(now_ms);
}

void CaptureClient::completeDownload(bool decoded, uint32_t now_ms) {
  download_in_flight_ = false;
  if (decoded) {
    photo_updated_ = true;
    active_request_ = false;
    retry_download_ = false;
    state_ = ClientState::Photo;
    return;
  }
  // Keep the last displayed photo and retry only retrieval, never submit.
  retry_download_ = true;
  next_download_at_ = now_ms + 1000;
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
  reconnect_backoff_ms_ = reconnect_backoff_ms_ < 10000 ? reconnect_backoff_ms_ * 2 : 10000;
  state_ = ClientState::Connecting;
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
