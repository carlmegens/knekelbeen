#include <Arduino.h>
#include <ArduinoOTA.h>
#include <LittleFS.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>

#include "audio.h"
#include "config.h"
#include "candles.h"
#include "eyes.h"
#include "mic.h"
#include "jaw.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#endif

static WebServer server(80);
static String brainUrl;  // laptop app, announced by itself every 30 s

// web/index.html, embedded at build time (board_build.embed_txtfiles).
extern const char PAGE[] asm("_binary_web_index_html_start");

static void setupWifi() {
  WiFi.setHostname(HOSTNAME);
  if (strlen(WIFI_SSID)) {
    WiFi.mode(WIFI_STA);
    // Mesh/multi-AP: scan every channel and join the strongest AP, instead of
    // the first one found (the default).
    WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);
    WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("Connecting to %s", WIFI_SSID);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
      delay(250);
      Serial.print('.');
    }
    Serial.println();
    if (WiFi.status() != WL_CONNECTED)
      Serial.printf("WiFi failed (status %d) - is it a 2.4 GHz network?\n",
                    WiFi.status());
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi OK: http://%s  (http://%s.local)\n",
                  WiFi.localIP().toString().c_str(), HOSTNAME);
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.printf("AP mode: join '%s' / '%s', open http://%s\n", AP_SSID,
                  AP_PASSWORD, WiFi.softAPIP().toString().c_str());
  }
  WiFi.setSleep(false);  // lower latency for later audio streaming
  MDNS.begin(HOSTNAME);
  MDNS.addService("http", "tcp", 80);
}

static void setupServer() {
  server.on("/", [] { server.send(200, "text/html; charset=utf-8", PAGE); });

  server.on("/jaw", [] {
    jaw::setSmoothing(0.5f);
    jaw::setTarget(server.arg("pos").toFloat() / 100.0f);
    server.send(200, "text/plain", "ok");
  });

  server.on("/chatter", [] {
    jaw::setSmoothing(0.5f);
    uint32_t ms = server.hasArg("ms") ? server.arg("ms").toInt() : 3000;
    jaw::chatter(ms);
    server.send(200, "text/plain", "ok");
  });

  // Direct servo angle for calibration; cleared by the next jaw command.
  server.on("/raw", [] {
    jaw::setRawDeg(server.arg("deg").toInt());
    server.send(200, "text/plain", "ok");
  });

  server.on("/cal", [] {
    if (server.hasArg("closed") && server.hasArg("open")) {
      jaw::setCalibration(server.arg("closed").toInt(),
                          server.arg("open").toInt());
      jaw::setTarget(0);
    }
    server.send(200, "application/json",
                String("{\"closed\":") + jaw::closedDeg() +
                    ",\"open\":" + jaw::openDeg() + "}");
  });

  server.on("/random", [] {
    bool ok = audio::playRandom();
    server.send(ok ? 200 : 404, "text/plain", ok ? "ok" : "no clips");
  });

  server.on("/play", [] {
    String f = "/clips/" + server.arg("f");
    if (!audio::isValidWav(f)) {  // missing, empty or not a playable WAV
      server.send(415, "text/plain", "not a playable WAV");
      return;
    }
    server.send(audio::playFile(f) ? 200 : 404, "text/plain", "ok");
  });

  server.on("/tone", [] {
    audio::playTone();
    server.send(200, "text/plain", "ok");
  });

  server.on("/pins", [] {
    if (server.hasArg("bclk"))
      audio::setPins(server.arg("bclk").toInt(), server.arg("lrc").toInt(),
                     server.arg("din").toInt());
    server.send(200, "application/json", audio::pins());
  });

  server.on("/stop", [] {
    audio::stop();
    server.send(200, "text/plain", "ok");
  });

  server.on("/volume", [] {
    audio::setVolume(server.arg("v").toInt());
    server.send(200, "text/plain", "ok");
  });

  server.on("/sync", [] {
    if (server.hasArg("gate"))
      audio::setSync({(int)server.arg("gate").toInt(),
                      (int)server.arg("sens").toInt(),
                      (int)server.arg("lead").toInt()});
    audio::Sync s = audio::sync();
    server.send(200, "application/json",
                String("{\"gate\":") + s.gate + ",\"sens\":" + s.sensitivity +
                    ",\"lead\":" + s.leadMs + ",\"vol\":" + audio::volume() +
                    "}");
  });

  server.on("/clips", [] {
    String json = "{\"clips\":[";
    File dir = LittleFS.open("/clips");
    bool first = true;
    for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
      if (!first) json += ',';
      first = false;
      json += String("{\"name\":\"") + f.name() + "\",\"size\":" + f.size() + "}";
    }
    json += String("],\"free\":") + (LittleFS.totalBytes() - LittleFS.usedBytes()) + "}";
    server.send(200, "application/json", json);
  });

  server.on("/delete", [] {
    String name = server.arg("f");
    bool ok = name.length() && name.indexOf('/') < 0 &&
              LittleFS.remove("/clips/" + name);
    server.send(ok ? 200 : 404, "text/plain", ok ? "ok" : "not found");
  });

  // Multipart upload into /clips (curl -F f=@hello.wav http://skull/upload)
  // 200 = ok, 415 = not a playable WAV, 507 = storage full.
  static File uploadFile;
  static String uploadPath;
  static bool uploadFull;
  server.on(
      "/upload", HTTP_POST,
      [] {
        if (uploadFile) uploadFile.close();  // make sure it can be removed
        if (uploadFull) {
          LittleFS.remove(uploadPath);
          server.send(507, "text/plain", "storage full");
        } else if (!audio::isValidWav(uploadPath)) {
          LittleFS.remove(uploadPath);
          server.send(415, "text/plain", "not a 16-bit PCM WAV");
        } else {
          server.send(200, "text/plain", "ok");
        }
      },
      [] {
        HTTPUpload &up = server.upload();
        if (up.status == UPLOAD_FILE_START) {
          String name = up.filename;
          name = name.substring(name.lastIndexOf('/') + 1);
          uploadPath = "/clips/" + name;
          uploadFull = false;
          uploadFile = LittleFS.open(uploadPath, "w");
          if (!uploadFile) uploadFull = true;
          Serial.printf("Upload %s\n", name.c_str());
        } else if (up.status == UPLOAD_FILE_WRITE && uploadFile) {
          if (uploadFile.write(up.buf, up.currentSize) != up.currentSize)
            uploadFull = true;
        } else if (up.status == UPLOAD_FILE_END && uploadFile) {
          uploadFile.close();
          Serial.printf("Upload done, %u bytes\n", up.totalSize);
        } else if (up.status == UPLOAD_FILE_ABORTED && uploadFile) {
          uploadFile.close();
          uploadFull = true;
        }
      });

  server.on("/eyes", [] {
    if (server.hasArg("color"))
      eyes::set(strtoul(server.arg("color").c_str(), nullptr, 16),
                server.arg("bright").toInt(),
                (eyes::Mode)server.arg("mode").toInt());
    if (server.hasArg("flash")) eyes::flash();
    char buf[64];
    snprintf(buf, sizeof buf, "{\"color\":\"%06X\",\"bright\":%d,\"mode\":%d}",
             (unsigned)eyes::color(), eyes::brightness(), (int)eyes::mode());
    server.send(200, "application/json", buf);
  });

  server.on("/candles", [] {
    if (server.hasArg("count"))
      candles::configure(server.arg("count").toInt(), server.arg("order"),
                         server.arg("bright").toInt(),
                         (candles::Mode)server.arg("mode").toInt());
    if (server.hasArg("speed")) candles::setSpeed(server.arg("speed").toInt());
    if (server.hasArg("voice")) candles::setVoiceReact(server.arg("voice") == "1");
    String fx = server.arg("effect");
    if (fx == "out") candles::trigger(candles::BLOW_OUT);
    else if (fx == "flare") candles::trigger(candles::FLARE);
    else if (fx == "ghost") candles::trigger(candles::GHOST);
    else if (fx == "test") candles::trigger(candles::TEST);
    server.send(200, "application/json", candles::json());
  });

  // The laptop app announces itself here so this page can reach the AI.
  server.on("/brain", [] {
    String url = server.arg("url");
    if (url.startsWith("http://") && url.length() < 80 && url.indexOf('"') < 0)
      brainUrl = url;
    server.send(200, "text/plain", brainUrl);
  });

  server.on("/mic", [] {
    if (server.hasArg("gain")) mic::setGain(server.arg("gain").toInt());
    char buf[128];
    snprintf(buf, sizeof buf,
             "{\"db\":%.1f,\"gain\":%d,\"streaming\":%s,\"slot\":%d,\"peak\":%u}",
             mic::levelDb(), mic::gain(), mic::streaming() ? "true" : "false",
             mic::slot(), (unsigned)mic::peak());
    server.send(200, "application/json", buf);
  });

  server.on("/status", [] {
    server.send(200, "application/json",
                String("{\"playing\":") + (audio::isPlaying() ? "true" : "false") +
                    ",\"live\":" + (audio::isLive() ? "true" : "false") +
                    ",\"brain\":\"" + brainUrl + "\"" +
                    ",\"clip\":\"" + audio::currentClip() + "\"}");
  });

  server.begin();
}

static void setupOta() {
  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([] { audio::stop(); });
  ArduinoOTA.begin();
}

// Serial: send a number 0-100 to set jaw %, 'c' to chatter.
static void handleSerial() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      line.trim();
      if (line == "c") jaw::chatter(3000);
      else if (line.length()) jaw::setTarget(line.toFloat() / 100.0f);
      line = "";
    } else {
      line += ch;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\n=== Talking Skull ===");
  jaw::begin();
  eyes::begin();
  candles::begin();
  mic::begin();
  audio::begin();
  setupWifi();
  audio::beginNetwork();
  mic::beginNetwork();
  setupServer();
  setupOta();
}

// The ESP32 never roams on its own. If the signal stays weak (e.g. it booted
// near another AP), scan in the background and move to a clearly stronger AP
// of the same network. Never while talking, so a conversation isn't cut off.
static void checkRoaming() {
  static uint32_t weakSince = 0, nextTry = 0;
  static bool scanning = false;
  if (WiFi.getMode() != WIFI_STA || WiFi.status() != WL_CONNECTED) return;

  if (scanning) {
    int n = WiFi.scanComplete();
    if (n == WIFI_SCAN_RUNNING) return;
    scanning = false;
    int best = -1, current = WiFi.RSSI();
    for (int i = 0; i < n; i++)
      if (WiFi.SSID(i) == WIFI_SSID && WiFi.BSSIDstr(i) != WiFi.BSSIDstr() &&
          (best < 0 || WiFi.RSSI(i) > WiFi.RSSI(best)))
        best = i;
    if (best >= 0 && WiFi.RSSI(best) >= current + ROAM_MIN_GAIN && !audio::isPlaying()) {
      Serial.printf("Roaming: %d dBm -> %d dBm (%s)\n", current, WiFi.RSSI(best),
                    WiFi.BSSIDstr(best).c_str());
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WiFi.channel(best), WiFi.BSSID(best));
    } else {
      nextTry = millis() + ROAM_BACKOFF_MS;  // nothing better around
    }
    WiFi.scanDelete();
    return;
  }

  if (WiFi.RSSI() > ROAM_RSSI || audio::isPlaying()) {
    weakSince = 0;
    return;
  }
  if (!weakSince) weakSince = millis();
  if (millis() - weakSince > ROAM_AFTER_MS && (int32_t)(millis() - nextTry) >= 0) {
    weakSince = 0;
    scanning = WiFi.scanNetworks(true) == WIFI_SCAN_RUNNING;  // async
  }
}

static void printStatus() {
  if (WiFi.getMode() == WIFI_AP)
    Serial.printf("[status] AP '%s' http://%s\n", AP_SSID,
                  WiFi.softAPIP().toString().c_str());
  else
    Serial.printf("[status] WiFi %s (%d) http://%s rssi=%d\n",
                  WiFi.status() == WL_CONNECTED ? "connected" : "DOWN",
                  WiFi.status(), WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
}

void loop() {
  static uint32_t lastStatus = 0, lastRoam = 0;
  if (millis() - lastRoam > 1000) {
    lastRoam = millis();
    checkRoaming();
  }
  if (millis() - lastStatus > 10000) {
    lastStatus = millis();
    printStatus();
  }
  server.handleClient();
  ArduinoOTA.handle();
  handleSerial();
  delay(1);
}
