#pragma once

#include <cstddef>
#include <cstdint>

// What the power chip reports about charging. Unknown is a real answer on the
// StickS3 (M5Unified returns charge_unknown when the PM1 cannot tell), so it is
// carried through rather than collapsed into "not charging".
enum class ChargeState : uint8_t { Discharging, Charging, Unknown };

// Chooses what the "+" mark means. On the StickS3 the charger's CHG_STAT pin
// (what M5Unified's isCharging() reads) cycles on and off for ~20 s at a time
// with the cable attached, so when the PM1 can report its power source the mark
// follows "external power present" and the pin is ignored. Only when the source
// is unknown does the charger pin's report stand.
ChargeState chargeStateFrom(bool power_source_known, bool external_power, ChargeState charger_report);

// Owns the battery text shown in the corner of every screen and decides how
// often the power chip is read. No Arduino or M5Unified dependency, so it runs
// under the native Unity tests; main.cpp feeds it M5.Power readings.
class BatteryMonitor {
 public:
  static constexpr uint32_t kPollIntervalMs = 10000;
  static constexpr int kLowPercent = 15;
  // The PM1 level is derived from voltage, which sags under the Wi-Fi radio's
  // load, so successive readings swing by up to five or six points. Readings
  // are first averaged (weight 1/2^kSmoothingShift per poll, a time constant
  // of about four polls), then the shown level holds until the average differs
  // from it by kHysteresisPercent.
  static constexpr int kSmoothingShift = 2;
  static constexpr int kHysteresisPercent = 3;
  // With USB attached, the PM1 charger status pin reads "not charging" for a
  // single poll now and then. Leaving the charging state needs this many
  // consecutive discharging readings; entering it is immediate.
  static constexpr int kDischargeConfirmPolls = 2;
  static constexpr size_t kLabelSize = 8;

  // True before the first update and every kPollIntervalMs after the last one.
  bool pollDue(uint32_t now_ms) const;
  // Records a reading. Returns true when the visible label changed, so the UI
  // redraws only then. Negative level means unknown; values are clamped 0..100.
  // Small moves inside kHysteresisPercent of the shown level are absorbed and
  // a lone discharging sample does not clear the charging mark; an unknown
  // level or a recovery from unknown always shows at once, and an unknown
  // charge state leaves the shown mark alone.
  bool update(int level_percent, ChargeState charge, uint32_t now_ms);
  // "87%", "87%+" while charging, "--%" when unknown.
  const char* label() const { return label_; }
  // The level currently shown, which lags the raw reading by the deadband.
  int level() const { return level_; }
  // Known, at or below kLowPercent, and not charging.
  bool low() const;

 private:
  char label_[kLabelSize] = "--%";
  int level_ = -1;
  int filtered16_ = -1;  // running average in 1/16 percent; negative = no history
  ChargeState charge_ = ChargeState::Unknown;
  int discharging_streak_ = 0;
  bool polled_ = false;
  uint32_t last_poll_ms_ = 0;
};
