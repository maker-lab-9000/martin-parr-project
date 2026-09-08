#include "display.h"

#include <M5Unified.h>
#include <JPEGDEC.h>

#include <algorithm>
#include <cstdio>
#include <cstring>

namespace {
constexpr uint16_t kBars[] = {TFT_WHITE, TFT_YELLOW, TFT_CYAN, TFT_GREEN,
                              TFT_MAGENTA, TFT_RED, TFT_BLUE, TFT_BLACK};

int validateJpegDraw(JPEGDRAW*) {
  // Validation decodes every MCU but intentionally discards its pixels. M5GFX
  // does the visible decode only after this complete pass has succeeded.
  return 1;
}

bool decodesSuccessfully(const uint8_t* jpeg, size_t size) {
  if (jpeg == nullptr || size < 4 || size > StickDisplay::kMaxJpegBytes) return false;
  // JPEGDEC contains ~18 KiB of workspace, exceeding loopTask's 8 KiB stack.
  // Only the UI loop calls this function, so reuse one static decoder safely.
  static JPEGDEC decoder;
  if (!decoder.openRAM(const_cast<uint8_t*>(jpeg), static_cast<int>(size), validateJpegDraw)) return false;
  const bool decoded = decoder.decode(0, 0, 0) == 1;
  decoder.close();
  return decoded;
}
}

void StickDisplay::begin() {
  M5.Display.setRotation(1);
  width_ = M5.Display.width();
  height_ = M5.Display.height();
  M5.Display.setTextDatum(middle_center);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  drawColourBars();
}

void StickDisplay::drawColourBars() {
  constexpr size_t bar_count = sizeof(kBars) / sizeof(kBars[0]);
  const int16_t bar_width = std::max<int16_t>(1, width_ / static_cast<int16_t>(bar_count));
  for (size_t index = 0; index < bar_count; ++index) {
    const int16_t x = static_cast<int16_t>(index * bar_width);
    const int16_t w = index + 1 == bar_count ? width_ - x : bar_width;
    M5.Display.fillRect(x, 0, w, height_, kBars[index]);
  }
  M5.Display.fillRect(0, height_ - 24, width_, 24, TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  // Centred in the space left of the battery badge, not under it.
  M5.Display.drawString("READY  •  press primary button", (width_ - kBatteryBadgeWidth) / 2, height_ - 12);
}

void StickDisplay::setBatteryLabel(const char* label, bool low) {
  std::strncpy(battery_label_, label == nullptr ? "" : label, sizeof(battery_label_) - 1);
  battery_label_[sizeof(battery_label_) - 1] = '\0';
  battery_low_ = low;
  drawBatteryBadge();
}

void StickDisplay::drawBatteryBadge() {
  if (battery_label_[0] == '\0') return;
  const int16_t x = width_ - kBatteryBadgeWidth;
  const int16_t y = height_ - kBatteryBadgeHeight;
  M5.Display.fillRect(x, y, kBatteryBadgeWidth, kBatteryBadgeHeight, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(middle_center);
  // Red below the low threshold while discharging; white otherwise. The trailing
  // "+" in the label marks charging.
  M5.Display.setTextColor(battery_low_ ? TFT_RED : TFT_WHITE, TFT_BLACK);
  M5.Display.drawString(battery_label_, x + kBatteryBadgeWidth / 2, y + kBatteryBadgeHeight / 2);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
}

void StickDisplay::drawMessageElapsed(uint32_t elapsed_seconds) {
  // Clear only the counter's own box (up to "120s" at size 1) before redrawing,
  // so "9s" fully replaces "10s" without touching the title or detail lines.
  M5.Display.fillRect(width_ / 2 - 18, height_ / 2 + 19, 36, 14, TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(middle_center);
  char elapsed[24];
  snprintf(elapsed, sizeof(elapsed), "%lus", static_cast<unsigned long>(elapsed_seconds));
  M5.Display.drawString(elapsed, width_ / 2, height_ / 2 + 26);
}

void StickDisplay::drawMessage(const char* title, const char* detail, uint32_t elapsed_seconds) {
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.drawString(title, width_ / 2, height_ / 2 - 22);
  M5.Display.setTextSize(1);
  M5.Display.drawString(detail, width_ / 2, height_ / 2 + 4);
  drawMessageElapsed(elapsed_seconds);
}

void StickDisplay::drawOverlayElapsed(uint32_t elapsed_seconds) {
  // The counter sits at the right end of the black top strip; clear its box only.
  M5.Display.fillRect(width_ - 32, 0, 32, 14, TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setTextDatum(middle_center);
  char elapsed[24];
  snprintf(elapsed, sizeof(elapsed), "%lus", static_cast<unsigned long>(elapsed_seconds));
  M5.Display.drawString(elapsed, width_ - 14, 7);
}

void StickDisplay::drawBarsOverlay(const char* title, const char* detail, uint32_t elapsed_seconds) {
  drawColourBars();
  M5.Display.fillRect(0, 0, width_, 32, TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.drawString(title, width_ / 2, 7);
  M5.Display.drawString(detail, width_ / 2, 18);
  drawOverlayElapsed(elapsed_seconds);
}

void StickDisplay::drawElapsedOnly(ClientState state, uint32_t elapsed_seconds) {
  switch (state) {
    case ClientState::Requesting:
    case ClientState::Processing:
    case ClientState::Downloading:
      drawOverlayElapsed(elapsed_seconds);
      break;
    case ClientState::Connecting:
      drawMessageElapsed(elapsed_seconds);
      break;
    case ClientState::Error:
      // The error screen shows a counter only when there is no photo behind it.
      if (!hasPhoto()) drawMessageElapsed(elapsed_seconds);
      break;
    case ClientState::Ready:
    case ClientState::Photo:
      break;
  }
}

void StickDisplay::drawPhoto() {
  if (photo_size_ == 0) return;
  const int16_t target_width = std::min<int16_t>(width_, (height_ * 240) / 135);
  const int16_t target_height = std::min<int16_t>(height_, (width_ * 135) / 240);
  const int16_t x = (width_ - target_width) / 2;
  const int16_t y = (height_ - target_height) / 2;
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.drawJpg(photo_, photo_size_, x, y, target_width, target_height);
}

bool StickDisplay::decodeAndStore(const uint8_t* jpeg, size_t jpeg_size) {
  if (!decodesSuccessfully(jpeg, jpeg_size)) {
    return false;
  }
  // M5GFX exposes a draw-based decoder. JPEGDEC completed the candidate
  // decode above, so only a verified image can replace the persistent buffer.
  const int16_t target_width = std::min<int16_t>(width_, (height_ * 240) / 135);
  const int16_t target_height = std::min<int16_t>(height_, (width_ * 135) / 240);
  const int16_t x = (width_ - target_width) / 2;
  const int16_t y = (height_ - target_height) / 2;
  M5.Display.drawJpg(jpeg, jpeg_size, x, y, target_width, target_height);
  std::memcpy(photo_, jpeg, jpeg_size);
  photo_size_ = jpeg_size;
  return true;
}

void StickDisplay::render(const CaptureClient& client, uint32_t now_ms) {
  const ClientState state = client.state();
  const uint32_t elapsed = client.elapsedSeconds(now_ms);
  const bool ready = client.readyForCapture();
  // Only the photo screen draws anything that depends on readiness. During a
  // capture the Pi reports itself busy, which flips `ready`; that must not
  // trigger a full repaint of the colour bars.
  const bool ready_matters = state == ClientState::Photo;
  const bool screen_changed = state != last_state_ || (ready_matters && ready != last_ready_);
  const bool counter_changed = elapsed != last_elapsed_seconds_;
  if (!screen_changed && !counter_changed) return;
  last_state_ = state;
  last_elapsed_seconds_ = elapsed;
  last_ready_ = ready;
  if (!screen_changed) {
    // Once a second while waiting: repaint the seconds box, nothing else.
    drawElapsedOnly(state, elapsed);
    return;
  }
  switch (state) {
    case ClientState::Ready:
      drawColourBars();
      break;
    case ClientState::Connecting:
      drawMessage("CONNECTING", "Wi-Fi reconnecting", elapsed);
      break;
    case ClientState::Requesting:
      drawBarsOverlay("REQUESTING", "Sending capture request", elapsed);
      break;
    case ClientState::Processing:
      drawBarsOverlay("PROCESSING", "Waiting for film scan", elapsed);
      break;
    case ClientState::Downloading:
      drawBarsOverlay("DOWNLOADING", "Fetching 240 x 135 preview", elapsed);
      break;
    case ClientState::Photo:
      drawPhoto();
      if (!ready) {
        M5.Display.fillRect(0, 0, width_, 20, TFT_BLACK);
        M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
        M5.Display.setTextSize(1);
        M5.Display.drawString("Pi unavailable or busy", width_ / 2, 10);
      }
      break;
    case ClientState::Error:
      if (!hasPhoto()) {
        drawMessage(client.timedOut() ? "TIMEOUT" : "ERROR", client.errorDetail(), elapsed);
        break;
      }
      drawPhoto();
      M5.Display.fillRect(0, 0, width_, 20, TFT_BLACK);
      M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
      M5.Display.setTextSize(1);
      M5.Display.drawString(client.errorDetail(), width_ / 2, 10);
      break;
  }
  // Every branch above repainted the full screen, so the badge goes back on top.
  drawBatteryBadge();
}
