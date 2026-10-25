#include "turn.h"

#include <Preferences.h>

#include "audio.h"
#include "config.h"

namespace turn {

static Preferences prefs;
static volatile int center = TURN_CENTER_DEG_DEFAULT;
static volatile int range = TURN_RANGE_DEG_DEFAULT;
static volatile bool lively = true;
static volatile bool enabled = false;  // off until the neck is built
static volatile float targetPos = 0;
static volatile int rawDeg = -1;
static volatile uint32_t manualUntil = 0;  // lively mode waits after a manual move

// LEDC channel 2 runs on its own timer, next to the jaw's channel 0.
namespace servo {
static const int CH = 2, BITS = 14, HZ = 50;
static bool attached = false;
static void write(float deg) {
  float us = 500 + constrain(deg, 0.0f, 180.0f) * 2000 / 180;
  uint32_t duty = us * ((1 << BITS) - 1) / (1000000 / HZ);
  if (!attached) {
    ledcSetup(CH, HZ, BITS);
    ledcWrite(CH, duty);  // before the pin goes live, so no stray first pulse
    ledcAttachPin(PIN_TURN_SERVO, CH);
    attached = true;
  } else {
    ledcWrite(CH, duty);
  }
}
static void release() {
  if (!attached) return;
  ledcDetachPin(PIN_TURN_SERVO);
  pinMode(PIN_TURN_SERVO, OUTPUT);
  digitalWrite(PIN_TURN_SERVO, LOW);
  attached = false;
}
}  // namespace servo

static float posToDeg(float p) { return center + constrain(p, -1.0f, 1.0f) * range; }

// Picks where to look while talking: mostly small turns, now and then a
// bigger look to one side, and back to the middle when it's quiet.
static void livelyStep(uint32_t now) {
  static uint32_t nextGlance = 0, quietSince = 0;
  if (!lively || rawDeg >= 0 || now < manualUntil) return;
  if (audio::isPlaying()) {
    quietSince = 0;
    if (now >= nextGlance) {
      float p = random(-100, 101) / 100.0f;
      targetPos = random(100) < 70 ? p * 0.4f : p;
      nextGlance = now + random(1800, 5000);
    }
  } else {
    if (!quietSince) quietSince = now;
    if (now - quietSince > 2500) targetPos = 0;
    nextGlance = 0;
  }
}

static void turnTask(void *) {
  const TickType_t period = pdMS_TO_TICKS(20);
  TickType_t last = xTaskGetTickCount();
  float from = center, to = center, deg = center;
  uint32_t moveStart = 0, moveMs = 0, restSince = 0;
  if (enabled) servo::write(deg);
  for (;;) {
    uint32_t now = millis();
    if (!enabled) {
      servo::release();
      vTaskDelayUntil(&last, period);
      continue;
    }
    livelyStep(now);
    float want = rawDeg >= 0 ? rawDeg : posToDeg(targetPos);
    if (fabsf(want - to) > 0.4f) {  // new destination: start a fresh S-curve
      from = deg;
      to = want;
      // ~0.5 s for a small turn, ~1.2 s for the full sweep at the default range.
      moveMs = 350 + (uint32_t)(fabsf(to - from) * 16);
      moveStart = now;
    }
    if (deg != to) {
      float t = moveMs ? constrain((now - moveStart) / (float)moveMs, 0.0f, 1.0f) : 1;
      float s = t * t * t * (t * (t * 6 - 15) + 10);  // smootherstep
      deg = t >= 1 ? to : from + (to - from) * s;
      servo::write(deg);
      restSince = now;
    } else if (!audio::isPlaying() && now - restSince > TURN_IDLE_RELEASE_MS) {
      // Hold while talking (the mic is muted then anyway): a slack servo lets
      // the head drift or spring back on the wires, and the next move jerks.
      servo::release();
    }
    vTaskDelayUntil(&last, period);
  }
}

void begin() {
  prefs.begin("turn", false);
  center = prefs.getInt("center", TURN_CENTER_DEG_DEFAULT);
  range = prefs.getInt("range", TURN_RANGE_DEG_DEFAULT);
  lively = prefs.getBool("lively", true);
  enabled = prefs.getBool("on", false);
  xTaskCreatePinnedToCore(turnTask, "turn", 3072, nullptr, 3, nullptr, 1);
}

void setTarget(float pos) {
  rawDeg = -1;
  targetPos = constrain(pos, -1.0f, 1.0f);
  manualUntil = millis() + 10000;
}

float target() { return targetPos; }

void setRawDeg(int deg) { rawDeg = constrain(deg, 0, 180); }

void setConfig(bool on, int c, int r, bool l) {
  enabled = on;
  prefs.putBool("on", enabled);
  center = constrain(c, 0, 180);
  range = constrain(r, 0, TURN_RANGE_DEG_MAX);
  lively = l;
  rawDeg = -1;
  prefs.putInt("center", center);
  prefs.putInt("range", range);
  prefs.putBool("lively", lively);
}

String json() {
  return String("{\"enabled\":") + (enabled ? "true" : "false") +
         ",\"center\":" + center + ",\"range\":" + range +
         ",\"lively\":" + (lively ? "true" : "false") +
         ",\"pos\":" + String(targetPos, 2) + "}";
}

}  // namespace turn
