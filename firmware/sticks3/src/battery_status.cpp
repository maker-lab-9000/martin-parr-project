#include "battery_status.h"

#include <cstdio>
#include <cstring>

ChargeState chargeStateFrom(bool power_source_known, bool external_power, ChargeState charger_report) {
  if (!power_source_known) return charger_report;
  return external_power ? ChargeState::Charging : ChargeState::Discharging;
}

bool BatteryMonitor::pollDue(uint32_t now_ms) const {
  return !polled_ || now_ms - last_poll_ms_ >= kPollIntervalMs;
}

bool BatteryMonitor::update(int level_percent, ChargeState charge, uint32_t now_ms) {
  polled_ = true;
  last_poll_ms_ = now_ms;
  const int reading = level_percent < 0 ? -1 : (level_percent > 100 ? 100 : level_percent);
  if (reading < 0) {
    // Unknown is shown at once and clears the history, so the next known
    // reading is taken as-is instead of being averaged with stale values.
    filtered16_ = -1;
    level_ = -1;
  } else {
    if (filtered16_ < 0) {
      filtered16_ = reading * 16;
    } else {
      filtered16_ += (reading * 16 - filtered16_) / (1 << kSmoothingShift);
    }
    const int smoothed = (filtered16_ + 8) / 16;
    const int delta = smoothed - level_;
    const bool inside_deadband =
        level_ >= 0 && delta < kHysteresisPercent && delta > -kHysteresisPercent;
    if (!inside_deadband) level_ = smoothed;
  }

  switch (charge) {
    case ChargeState::Charging:
      charge_ = ChargeState::Charging;
      discharging_streak_ = 0;
      break;
    case ChargeState::Discharging:
      if (charge_ != ChargeState::Charging || ++discharging_streak_ >= kDischargeConfirmPolls) {
        charge_ = ChargeState::Discharging;
        discharging_streak_ = 0;
      }
      break;
    case ChargeState::Unknown:
      // No information; keep showing the last known state.
      break;
  }

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
