#include <Arduino.h>
#include <HTTPClient.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <esp_system.h>

#include <algorithm>

#include "battery_status.h"
#include "capture_client.h"
#include "display.h"

// Task 4 injects these build flags or a generated local configuration file.
// Empty defaults intentionally leave this firmware unable to join a network.
#ifndef STICKS3_WIFI_SSID
#define STICKS3_WIFI_SSID ""
#endif
#ifndef STICKS3_WIFI_PASSWORD
#define STICKS3_WIFI_PASSWORD ""
#endif
#ifndef STICKS3_API_BASE
#define STICKS3_API_BASE ""
#endif
#ifndef STICKS3_API_TOKEN
#define STICKS3_API_TOKEN ""
#endif

namespace {
CaptureClient capture;
StickDisplay display;
BatteryMonitor battery;
SemaphoreHandle_t capture_mutex = nullptr;
SemaphoreHandle_t jpeg_mutex = nullptr;
TaskHandle_t network_task = nullptr;
uint8_t jpeg_back_buffer[StickDisplay::kMaxJpegBytes];
size_t jpeg_back_size = 0;
bool jpeg_ready = false;

bool configured() {
  return STICKS3_WIFI_SSID[0] != '\0' && STICKS3_API_BASE[0] != '\0' && STICKS3_API_TOKEN[0] != '\0';
}

void lockClient() { xSemaphoreTake(capture_mutex, portMAX_DELAY); }
void unlockClient() { xSemaphoreGive(capture_mutex); }

String endpoint(const char* suffix) { return String(STICKS3_API_BASE) + suffix; }

void addAuth(HTTPClient& http) {
  http.addHeader("Authorization", String("Bearer ") + STICKS3_API_TOKEN);
}

JobStatus jobStatus(const String& payload) {
  if (payload.indexOf("\"state\":\"complete\"") >= 0) return JobStatus::Complete;
  if (payload.indexOf("\"state\":\"failed\"") >= 0) return JobStatus::Failed;
  if (payload.indexOf("\"state\":\"processing\"") >= 0) return JobStatus::Processing;
  return JobStatus::Pending;  // The server calls its initial state "queued".
}

String jsonString(const String& payload, const char* key) {
  const String prefix = String("\"") + key + "\":\"";
  const int start = payload.indexOf(prefix);
  if (start < 0) return String();
  const int value_start = start + prefix.length();
  const int end = payload.indexOf('"', value_start);
  return end < 0 ? String() : payload.substring(value_start, end);
}

bool serverReady(const String& payload) { return payload.indexOf("\"ready\":true") >= 0; }
bool serverHasActiveJob(const String& payload) { return payload.indexOf("\"active_capture_id\":null") < 0; }

bool fetchJpeg(const char* request_id) {
  HTTPClient http;
  const String path = endpoint((String("/v1/captures/") + request_id + "/image.jpg").c_str());
  if (!http.begin(path)) return false;
  http.setTimeout(5000);
  addAuth(http);
  const int status = http.GET();
  if (status != HTTP_CODE_OK) {
    http.end();
    return false;
  }
  const int length = http.getSize();
  if (length > static_cast<int>(StickDisplay::kMaxJpegBytes)) {
    http.end();
    return false;
  }
  WiFiClient* stream = http.getStreamPtr();
  size_t received = 0;
  const uint32_t deadline = millis() + 5000;
  while (http.connected() && (length < 0 || received < static_cast<size_t>(length)) && millis() < deadline) {
    const size_t available = stream->available();
    if (available == 0) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    const size_t room = StickDisplay::kMaxJpegBytes - received;
    if (room == 0) {
      http.end();
      return false;
    }
    const size_t count = stream->readBytes(jpeg_back_buffer + received, std::min(available, room));
    received += count;
  }
  http.end();
  if ((length >= 0 && received != static_cast<size_t>(length)) || received < 4 ||
      jpeg_back_buffer[0] != 0xff || jpeg_back_buffer[1] != 0xd8 ||
      jpeg_back_buffer[received - 2] != 0xff || jpeg_back_buffer[received - 1] != 0xd9) {
    return false;
  }
  xSemaphoreTake(jpeg_mutex, portMAX_DELAY);
  jpeg_back_size = received;
  jpeg_ready = true;
  xSemaphoreGive(jpeg_mutex);
  return true;
}

void processWork(const WorkItem& work) {
  const uint32_t now = millis();
  if (work.kind == WorkKind::Connect) {
    if (configured()) WiFi.begin(STICKS3_WIFI_SSID, STICKS3_WIFI_PASSWORD);
    lockClient();
    capture.completeConnect(configured() && WiFi.status() == WL_CONNECTED, now);
    unlockClient();
    return;
  }
  if (!configured()) return;

  HTTPClient http;
  if (work.kind == WorkKind::Status) {
    if (!http.begin(endpoint("/v1/status"))) {
      lockClient();
      capture.completeStatusTransportError(millis());
      unlockClient();
      return;
    }
    http.setTimeout(5000);
    addAuth(http);
    const int status = http.GET();
    const String payload = status == HTTP_CODE_OK ? http.getString() : String();
    http.end();
    lockClient();
    if (status == HTTP_CODE_OK) {
      const String instance_id = jsonString(payload, "instance_id");
      capture.completeServerStatus(serverReady(payload), serverHasActiveJob(payload), instance_id.c_str(), millis());
    } else {
      capture.completeStatusTransportError(millis());
    }
    unlockClient();
    return;
  }
  if (work.kind == WorkKind::Submit) {
    if (!http.begin(endpoint("/v1/captures"))) {
      lockClient();
      capture.submitStartFailed(millis());
      unlockClient();
      return;
    }
    http.setTimeout(5000);
    addAuth(http);
    http.addHeader("Content-Type", "application/json");
    const int status = http.POST(String("{\"request_id\":\"") + work.request_id + "\"}");
    http.end();
    lockClient();
    if (status >= 200 && status < 300) {
      capture.completeSubmit(true, millis());
    } else if (status >= 100) {
      // A completed HTTP response is a known rejection, not an ambiguous
      // acknowledgement. Release the button for a deliberate later press.
      capture.rejectSubmit(millis());
    } else {
      capture.completeSubmit(false, millis());
    }
    unlockClient();
    return;
  }
  if (work.kind == WorkKind::Poll) {
    const String path = endpoint((String("/v1/captures/") + work.request_id).c_str());
    if (!http.begin(path)) {
      lockClient();
      capture.completePollTransportError(millis());
      unlockClient();
      return;
    }
    http.setTimeout(5000);
    addAuth(http);
    const int status = http.GET();
    const String payload = status == HTTP_CODE_OK ? http.getString() : String();
    http.end();
    lockClient();
    if (status == HTTP_CODE_OK) {
      capture.acceptStatus(jobStatus(payload), millis());
    } else if (status == HTTP_CODE_NOT_FOUND) {
      capture.acceptStatus(JobStatus::Missing, millis());
    } else {
      capture.completePollTransportError(millis());
    }
    unlockClient();
    return;
  }
  if (work.kind == WorkKind::Download) {
    if (!fetchJpeg(work.request_id)) {
      lockClient();
      capture.completeDownload(false, millis());
      unlockClient();
    }
  }
}

void networkWorker(void*) {
  bool was_connected = false;
  for (;;) {
    const bool connected = configured() && WiFi.status() == WL_CONNECTED;
    if (connected != was_connected) {
      lockClient();
      capture.setWifiConnected(connected, millis());
      unlockClient();
      was_connected = connected;
    }
    WorkItem work;
    lockClient();
    work = capture.nextWork(millis());
    unlockClient();
    if (work.kind != WorkKind::None) processWork(work);
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void playShutter() { M5.Speaker.tone(1800, 55); }

ChargeState chargerPinReport() {
  switch (M5.Power.isCharging()) {
    case m5::Power_Class::is_charging: return ChargeState::Charging;
    case m5::Power_Class::is_discharging: return ChargeState::Discharging;
    default: return ChargeState::Unknown;
  }
}

// The PM1 reports which rails are powering the board. A reply of `none` means
// the read failed (a running board always has at least the battery), so that
// is treated as unknown and the charger pin decides.
ChargeState chargeState(uint8_t* sources_out) {
  const uint8_t sources = static_cast<uint8_t>(M5.Power.M5pm1.getPowerSource());
  *sources_out = sources;
  const bool known = sources != m5::M5PM1_Class::none;
  const bool external = (sources & (m5::M5PM1_Class::vin | m5::M5PM1_Class::vinout)) != 0;
  return chargeStateFrom(known, external, chargerPinReport());
}

// Reads the PM1 power chip on the monitor's cadence (every 10 s) and repaints
// the corner badge only when the visible text changes. Runs on the UI task,
// which owns the display; the I2C reads are short.
void pollBattery(uint32_t now_ms) {
  if (!battery.pollDue(now_ms)) return;
  const int level = static_cast<int>(M5.Power.getBatteryLevel());
  uint8_t sources = 0;
  const ChargeState charge = chargeState(&sources);
  if (battery.update(level, charge, now_ms)) {
    display.setBatteryLabel(battery.label(), battery.low());
    Serial.printf("[%lu] battery %s (level %d, %s, power sources 0x%02x, %d mV)\n",
                  static_cast<unsigned long>(now_ms), battery.label(), level,
                  charge == ChargeState::Charging ? "external power"
                  : charge == ChargeState::Discharging ? "on battery" : "power state unknown",
                  sources, M5.Power.getBatteryVoltage());
  }
}

void smokeTest() {
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextDatum(middle_center);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.drawString("StickS3 display / button / speaker", M5.Display.width() / 2, M5.Display.height() / 2);
  M5.Speaker.tone(1200, 80);
  delay(180);
}
}  // namespace

void setup() {
  auto config = M5.config();
  config.serial_baudrate = 115200;
  M5.begin(config);
  Serial.println("StickS3 remote capture boot");
  smokeTest();
  display.begin();
  capture_mutex = xSemaphoreCreateMutex();
  jpeg_mutex = xSemaphoreCreateMutex();
  WiFi.mode(WIFI_STA);
  xTaskCreatePinnedToCore(networkWorker, "capture-network", 8192, nullptr, 1, &network_task, 0);
}

void loop() {
  M5.update();
  lockClient();
  uint32_t words[] = {esp_random(), esp_random(), esp_random(), esp_random()};
  char id[37] = {};
  CaptureClient::makeUuid(words, id);
  capture.onButtonSample(M5.BtnA.isPressed(), millis(), id);
  if (capture.consumeShutterSound()) playShutter();
  if (xSemaphoreTake(jpeg_mutex, 0) == pdTRUE) {
    if (jpeg_ready) {
      jpeg_ready = false;
      capture.completeDownload(display.decodeAndStore(jpeg_back_buffer, jpeg_back_size), millis());
    }
    xSemaphoreGive(jpeg_mutex);
  }
  pollBattery(millis());
  display.render(capture, millis());
  unlockClient();
  delay(10);
}
