#include "smoke.h"

#include <HTTPClient.h>
#include <Preferences.h>

namespace smoke {

static Preferences prefs;
static bool enabled = false;
static String host;
static int cooldownS = 60, smallMs = 1500, bigMs = 5000, lead = 500;
static volatile int wanted = 0;  // 0 none, 1 small, 2 big
static volatile bool testing = false;
static uint32_t lastPuff = 0, offAt = 0;
static bool puffed = false, isOn = false;
static String lastResult = "nog niet gebruikt";

void begin() {
  prefs.begin("smoke", false);
  enabled = prefs.getBool("on", false);
  host = prefs.getString("host", "");
  cooldownS = prefs.getInt("cool", 60);
  smallMs = prefs.getInt("small", 1500);
  bigMs = prefs.getInt("big", 5000);
  lead = prefs.getInt("lead", 500);
}

int leadMs() { return lead; }

void setConfig(bool on, const String &h, int cool, int small, int big, int ld) {
  enabled = on;
  if (h.length() < 64 && h.indexOf('/') < 0 && h.indexOf('"') < 0) host = h;
  cooldownS = constrain(cool, 0, 3600);
  smallMs = constrain(small, 200, 10000);
  bigMs = constrain(big, 200, 10000);
  lead = constrain(ld, 0, 3000);
  prefs.putInt("lead", lead);
  prefs.putBool("on", enabled);
  prefs.putString("host", host);
  prefs.putInt("cool", cooldownS);
  prefs.putInt("small", smallMs);
  prefs.putInt("big", bigMs);
}

void puff(bool big, bool test) {
  testing |= test;
  wanted = max((int)wanted, big ? 2 : 1);
}

static int setSwitch(bool on) {
  HTTPClient http;
  http.setTimeout(1500);
  http.begin("http://" + host + "/rpc/Shelly.SetState");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(String("{\"id\":1,\"type\":0,\"state\":{\"state\":") + (on ? "true" : "false") + "}}");
  http.end();
  return code;
}

void service() {
  if (isOn && (int32_t)(millis() - offAt) >= 0) {
    // Retry until it's off; the Shelly's auto-off catches it if we can't.
    if (setSwitch(false) == 200 || millis() - offAt > 10000) isOn = false;
  }
  if (!wanted) return;
  bool big = wanted == 2, test = testing;
  wanted = 0;
  testing = false;
  if (!enabled || !host.length() || isOn) return;
  if (!test && puffed && millis() - lastPuff < (uint32_t)cooldownS * 1000) {
    lastResult = "overgeslagen (wachttijd)";
    return;
  }
  int code = setSwitch(true);
  lastPuff = millis();
  puffed = true;
  if (code == 200) {
    isOn = true;
    offAt = lastPuff + (big ? bigMs : smallMs);
    lastResult = big ? "veel rook" : "een beetje rook";
  } else {
    lastResult = "Shelly antwoordt niet (" + String(code) + ")";
  }
  Serial.printf("Smoke: %s\n", lastResult.c_str());
}

String json() {
  long ago = puffed ? (long)((millis() - lastPuff) / 1000) : -1;
  return String("{\"on\":") + (enabled ? "true" : "false") + ",\"host\":\"" + host +
         "\",\"cooldown\":" + cooldownS + ",\"small\":" + smallMs + ",\"big\":" + bigMs + ",\"lead\":" + lead +
         ",\"ago\":" + ago + ",\"result\":\"" + lastResult + "\"}";
}

}  // namespace smoke
