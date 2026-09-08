#pragma once

#include <cstddef>
#include <cstdint>

// What the power chip reports about charging. Unknown is a real answer on the
// StickS3 (M5Unified returns charge_unknown when the PM1 cannot tell), so it is
// carried through rather than collapsed into "not charging".
enum class ChargeState : uint8_t { Discharging, Charging, Unknown };

// Owns the battery text shown in the corner of every screen and decides how
// often the power chip is read. No Arduino or M5Unified dependency, so it runs
// under the native Unity tests; main.cpp feeds it M5.Power readings.
class BatteryMonitor {
 public:
  static constexpr uint32_t kPollIntervalMs = 10000;
  static constexpr int kLowPercent = 15;
  static constexpr size_t kLabelSize = 8;

  // True before the first update and every kPollIntervalMs after the last one.
  bool pollDue(uint32_t now_ms) const;
  // Records a reading. Returns true when the visible label changed, so the UI
  // redraws only then. Negative level means unknown; values are clamped 0..100.
  bool update(int level_percent, ChargeState charge, uint32_t now_ms);
  // "87%", "87%+" while charging, "--%" when unknown.
  const char* label() const { return label_; }
  int level() const { return level_; }
  // Known, at or below kLowPercent, and not charging.
  bool low() const;

 private:
  char label_[kLabelSize] = "--%";
  int level_ = -1;
  ChargeState charge_ = ChargeState::Unknown;
  bool polled_ = false;
  uint32_t last_poll_ms_ = 0;
};
