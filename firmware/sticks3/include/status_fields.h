#pragma once

// The Pi's UPS battery as published in GET /v1/status. `known` is false when
// the server has no UPS (`"pi_battery":null`), predates the field, or sent a
// value outside 0..100.
struct PiBattery {
  bool known = false;
  int percent = -1;
  bool external_power = false;
};

// Extracts pi_battery.percent and pi_battery.external_power from the status
// JSON. Deliberately small: the payload is produced by our own server, keys
// are unique, and this must run under the native tests without Arduino.
PiBattery parsePiBattery(const char* json);
