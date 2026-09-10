#include "status_fields.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

// Returns a pointer just past `"key":` (any spaces after the colon skipped), or nullptr.
const char* valueOf(const char* json, const char* key) {
  char quoted[48];
  std::snprintf(quoted, sizeof(quoted), "\"%s\"", key);
  const char* at = std::strstr(json, quoted);
  if (at == nullptr) return nullptr;
  at += std::strlen(quoted);
  while (*at == ' ') ++at;
  if (*at != ':') return nullptr;
  ++at;
  while (*at == ' ') ++at;
  return at;
}

}  // namespace

PiBattery parsePiBattery(const char* json) {
  PiBattery battery;
  if (json == nullptr) return battery;
  const char* object = valueOf(json, "pi_battery");
  if (object == nullptr || *object != '{') return battery;  // absent or null

  const char* percent = valueOf(object, "percent");
  const char* external = valueOf(object, "external_power");
  if (percent == nullptr || external == nullptr) return battery;

  char* end = nullptr;
  const long value = std::strtol(percent, &end, 10);
  if (end == percent || value < 0 || value > 100) return battery;

  battery.percent = static_cast<int>(value);
  battery.external_power = std::strncmp(external, "true", 4) == 0;
  battery.known = true;
  return battery;
}
