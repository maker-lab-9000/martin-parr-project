#include "battery_status.h"

#include <cstdio>
#include <cstring>

bool BatteryMonitor::pollDue(uint32_t now_ms) const {
  return !polled_ || now_ms - last_poll_ms_ >= kPollIntervalMs;
}

bool BatteryMonitor::update(int level_percent, ChargeState charge, uint32_t now_ms) {
  polled_ = true;
  last_poll_ms_ = now_ms;
  level_ = level_percent < 0 ? -1 : (level_percent > 100 ? 100 : level_percent);
  charge_ = charge;

  char next[kLabelSize];
  if (level_ < 0) {
    std::snprintf(next, sizeof(next), "--%%");
  } else {
    std::snprintf(next, sizeof(next), "%d%%%s", level_, charge_ == ChargeState::Charging ? "+" : "");
  }
  const bool changed = std::strcmp(next, label_) != 0;
  std::strncpy(label_, next, sizeof(label_) - 1);
  label_[sizeof(label_) - 1] = '\0';
  return changed;
}

bool BatteryMonitor::low() const {
  return level_ >= 0 && level_ <= kLowPercent && charge_ != ChargeState::Charging;
}
