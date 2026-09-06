#pragma once

#include <cstddef>
#include <cstdint>

#include "capture_client.h"

class StickDisplay {
 public:
  static constexpr size_t kMaxJpegBytes = 64 * 1024;

  void begin();
  void render(const CaptureClient& client, uint32_t now_ms);
  // Candidate bytes are decoded before they replace the persistent photo.
  bool decodeAndStore(const uint8_t* jpeg, size_t jpeg_size);
  bool hasPhoto() const { return photo_size_ > 0; }

 private:
  void drawPhoto();
  void drawColourBars();
  void drawMessage(const char* title, const char* detail, uint32_t elapsed_seconds);

  uint8_t photo_[kMaxJpegBytes] = {};
  size_t photo_size_ = 0;
  ClientState last_state_ = ClientState::Connecting;
  uint32_t last_elapsed_seconds_ = UINT32_MAX;
  int16_t width_ = 0;
  int16_t height_ = 0;
};
